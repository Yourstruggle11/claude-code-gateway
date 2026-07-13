"""Set up, validate, and run a local LiteLLM gateway for Claude Code."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv

MIN_PYTHON = (3, 10)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4000
DEFAULT_MODEL = "gemini-3.1-flash-lite"
PLACEHOLDERS = {"", "change-me", "your-api-key", "replace-me"}
CLAUDE_SETTINGS_SCHEMA = "https://json.schemastore.org/claude-code-settings.json"
CLAUDE_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
)


class GatewayError(RuntimeError):
    """An actionable error that should be shown without a traceback."""


@dataclass(frozen=True)
class Paths:
    root: Path
    env: Path
    config: Path


def _project_root() -> Path:
    """Find the clone root for editable installs and source checkouts."""
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        if (candidate / "config.yaml").is_file() and (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


def _paths(config: str | None = None) -> Paths:
    root = _project_root()
    configured = config or os.getenv("GATEWAY_CONFIG", "config.yaml")
    config_path = Path(configured).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    return Paths(root=root, env=root / ".env", config=config_path.resolve())


def _safe_value(value: object) -> str:
    return str(value or "").strip()


def _is_placeholder(value: object) -> bool:
    normalized = _safe_value(value).lower()
    return normalized in PLACEHOLDERS or normalized.startswith("your-")


def _load_environment(paths: Paths) -> None:
    if paths.env.is_file():
        load_dotenv(paths.env, override=False)


def _read_config(path: Path) -> dict:
    if not path.is_file():
        raise GatewayError(f"Configuration file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise GatewayError(f"Could not read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GatewayError(f"{path} must contain a YAML mapping at its top level.")
    models = data.get("model_list")
    if not isinstance(models, list) or not models:
        raise GatewayError(f"{path} must define at least one model under model_list.")
    return data


def _model_aliases(config: Mapping[str, object]) -> set[str]:
    aliases: set[str] = set()
    models = config.get("model_list", [])
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict) and item.get("model_name"):
                aliases.add(str(item["model_name"]))
    return aliases


def _environment_references(value: object) -> set[str]:
    if isinstance(value, str) and value.startswith("os.environ/"):
        return {value.removeprefix("os.environ/")}
    if isinstance(value, dict):
        return set().union(*(_environment_references(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_environment_references(item) for item in value))
    return set()


def _validate_runtime(paths: Paths) -> dict:
    if sys.version_info < MIN_PYTHON:
        version = ".".join(map(str, MIN_PYTHON))
        raise GatewayError(f"Python {version} or newer is required.")
    if not paths.env.is_file():
        raise GatewayError("Missing .env. Run `claude-gateway setup` first.")
    _load_environment(paths)
    config = _read_config(paths.config)
    missing = sorted(
        name for name in _environment_references(config) if _is_placeholder(os.getenv(name))
    )
    if missing:
        variables = ", ".join(missing)
        raise GatewayError(
            f"Missing required environment variables: {variables}. Add them to .env or the "
            "parent environment."
        )
    master_key = os.getenv("LITELLM_MASTER_KEY")
    if _is_placeholder(master_key) or len(_safe_value(master_key)) < 24:
        raise GatewayError("LITELLM_MASTER_KEY is missing or weak. Run `claude-gateway setup`.")
    aliases = _model_aliases(config)
    for variable, fallback in (
        ("GATEWAY_MODEL", DEFAULT_MODEL),
        ("GATEWAY_SMALL_MODEL", os.getenv("GATEWAY_MODEL", DEFAULT_MODEL)),
    ):
        model = os.getenv(variable, fallback)
        if model not in aliases:
            choices = ", ".join(sorted(aliases))
            raise GatewayError(f"{variable}={model!r} is not in model_list. Available: {choices}")
    return config


def _upsert_env(path: Path, updates: Mapping[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    if output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _litellm_command() -> str:
    suffix = ".exe" if os.name == "nt" else ""
    adjacent = Path(sys.executable).resolve().parent / f"litellm{suffix}"
    command = str(adjacent) if adjacent.is_file() else shutil.which("litellm")
    if not command:
        raise GatewayError(
            "LiteLLM is not installed in this environment. Re-run the installation step."
        )
    return command


def _claude_command() -> str:
    command = shutil.which("claude")
    if not command:
        raise GatewayError("Claude Code was not found. Install it, then run `claude doctor`.")
    return command


def _network_settings(args: argparse.Namespace) -> tuple[str, int]:
    host = getattr(args, "host", None) or os.getenv("GATEWAY_HOST", DEFAULT_HOST)
    argument_port = getattr(args, "port", None)
    raw_port = (
        argument_port if argument_port is not None else os.getenv("GATEWAY_PORT", str(DEFAULT_PORT))
    )
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise GatewayError(f"Invalid gateway port: {raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise GatewayError("Gateway port must be between 1 and 65535.")
    return host, port


def _proxy_command(paths: Paths, host: str, port: int) -> list[str]:
    return [
        _litellm_command(),
        "--config",
        str(paths.config),
        "--host",
        host,
        "--port",
        str(port),
        "--telemetry",
        "False",
    ]


def _proxy_environment() -> dict[str, str]:
    """Build a stable, quiet environment for LiteLLM's generic CLI variables."""
    environment = os.environ.copy()
    environment.pop("DEBUG", None)
    environment.pop("DETAILED_DEBUG", None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _wait_until_ready(host: str, port: int, process: subprocess.Popen, timeout: float) -> None:
    request_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{request_host}:{port}/health/liveliness"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise GatewayError(f"LiteLLM exited during startup with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.25)
    raise GatewayError(f"LiteLLM did not become ready at {url} within {timeout:g} seconds.")


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _confirm(prompt: str, *, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    response = input(f"{prompt} {suffix} ").strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}


def _claude_settings_path(paths: Paths, scope: str) -> Path:
    if scope == "local":
        return paths.root / ".claude" / "settings.local.json"
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    raise GatewayError(f"Unknown Claude Code settings scope: {scope}")


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GatewayError(f"Could not read Claude Code settings at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GatewayError(f"Claude Code settings at {path} must contain a JSON object.")
    env = data.get("env")
    if env is not None and not isinstance(env, dict):
        raise GatewayError(f"The env setting in {path} must be a JSON object.")
    return data


def _gateway_claude_settings(args: argparse.Namespace) -> tuple[dict[str, str], str]:
    host, port = _network_settings(args)
    base_host = "127.0.0.1" if host in {"0.0.0.0", "::", "localhost"} else host
    model = os.getenv("GATEWAY_MODEL", DEFAULT_MODEL)
    small_model = os.getenv("GATEWAY_SMALL_MODEL", model)
    environment = {
        "ANTHROPIC_BASE_URL": f"http://{base_host}:{port}",
        "ANTHROPIC_AUTH_TOKEN": os.environ["LITELLM_MASTER_KEY"],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": small_model,
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
    }
    return environment, model


def _write_json_with_backup(path: Path, data: Mapping[str, object]) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.bak")
        shutil.copy2(path, backup)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return backup


def command_configure_vscode(args: argparse.Namespace) -> int:
    paths = _paths(args.config)
    config = _validate_runtime(paths)
    settings_path = _claude_settings_path(paths, args.scope)
    settings = _read_json_object(settings_path)
    environment, model = _gateway_claude_settings(args)
    action = "remove gateway settings from" if args.remove else "configure"

    if args.dry_run:
        print(f"Would {action} Claude Code settings at {settings_path}.")
        print(f"Model: {model}")
        print(f"Gateway: {environment['ANTHROPIC_BASE_URL']}")
        print("Authentication token: [hidden]")
        print("No files changed (--dry-run).")
        return 0

    original = json.dumps(settings, sort_keys=True)
    if args.remove:
        existing_env = settings.get("env", {})
        if isinstance(existing_env, dict):
            for key in CLAUDE_ENV_KEYS:
                existing_env.pop(key, None)
            if existing_env:
                settings["env"] = existing_env
            else:
                settings.pop("env", None)
        if settings.get("model") in _model_aliases(config):
            settings.pop("model", None)
    else:
        settings.setdefault("$schema", CLAUDE_SETTINGS_SCHEMA)
        merged_env = dict(settings.get("env", {}))
        merged_env.update(environment)
        settings["env"] = merged_env
        settings["model"] = model

    if json.dumps(settings, sort_keys=True) == original:
        print(f"Claude Code settings already match the requested state at {settings_path}.")
        return 0

    backup = _write_json_with_backup(settings_path, settings)
    verb = "Removed gateway configuration from" if args.remove else "Configured"
    print(f"{verb} {settings_path} (authentication token hidden).")
    if backup:
        print(f"Backup created at {backup}.")
    if not args.remove:
        print("Next: run `claude-gateway start`, then open Claude Code in VS Code.")
    return 0


def command_setup(args: argparse.Namespace) -> int:
    paths = _paths(args.config)
    existing = dotenv_values(paths.env) if paths.env.exists() else {}
    config = _read_config(paths.config)
    provider_variables = _environment_references(config) - {"LITELLM_MASTER_KEY"}
    updates: dict[str, str] = {}
    for name in sorted(provider_variables):
        value = _safe_value(existing.get(name))
        if args.force or _is_placeholder(value):
            if not sys.stdin.isatty():
                raise GatewayError(
                    f"Interactive input is unavailable. Add {name} to .env and retry."
                )
            value = getpass.getpass(f"{name} (input hidden): ").strip()
            if _is_placeholder(value):
                raise GatewayError(f"A non-empty {name} value is required.")
        updates[name] = value
    master_key = _safe_value(existing.get("LITELLM_MASTER_KEY"))
    if args.force or _is_placeholder(master_key) or len(master_key) < 24:
        master_key = "sk-local-" + secrets.token_urlsafe(32)
    updates["LITELLM_MASTER_KEY"] = master_key
    _upsert_env(paths.env, updates)
    os.environ.update(updates)
    print(f"Configured {paths.env} (secrets were not displayed).")
    configure_vscode = bool(getattr(args, "configure_vscode", False))
    skip_vscode = bool(getattr(args, "no_configure_vscode", False))
    if not configure_vscode and not skip_vscode and sys.stdin.isatty():
        configure_vscode = _confirm("Configure the Claude Code VS Code extension for this project?")
    if configure_vscode:
        configure_args = argparse.Namespace(
            config=args.config,
            scope="local",
            dry_run=False,
            remove=False,
            host=None,
            port=None,
        )
        command_configure_vscode(configure_args)
    else:
        print("VS Code configuration skipped. Run `claude-gateway configure-vscode` when ready.")
    print("Next: run `claude-gateway doctor`, then start your preferred workflow.")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    paths = _paths(args.config)
    checks: list[tuple[str, str]] = []
    warnings: list[str] = []
    checks.append(("Python", sys.version.split()[0]))
    config = _validate_runtime(paths)
    checks.append(("Environment", f"{paths.env} (credentials present; values hidden)"))
    checks.append(("Configuration", str(paths.config)))
    checks.append(("Models", ", ".join(sorted(_model_aliases(config)))))
    checks.append(("LiteLLM", _litellm_command()))
    claude = shutil.which("claude")
    if claude:
        checks.append(("Claude Code", claude))
    else:
        warnings.append("Claude Code is not installed; standalone gateway commands still work.")
    host, port = _network_settings(args)
    checks.append(("Listener", f"{host}:{port}"))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        warnings.append(
            "The gateway is not bound to loopback; use TLS and stronger access controls."
        )
    if os.name != "nt" and paths.env.stat().st_mode & 0o077:
        warnings.append(".env is readable by other local users; run `chmod 600 .env`.")
    for name, detail in checks:
        print(f"[OK] {name}: {detail}")
    for warning in warnings:
        print(f"[WARN] {warning}")
    print("Doctor completed successfully.")
    return 0


def command_start(args: argparse.Namespace) -> int:
    paths = _paths(args.config)
    _validate_runtime(paths)
    host, port = _network_settings(args)
    print(f"Starting LiteLLM on http://{host}:{port} (Ctrl+C to stop).")
    try:
        return subprocess.run(
            _proxy_command(paths, host, port),
            cwd=paths.root,
            env=_proxy_environment(),
        ).returncode
    except KeyboardInterrupt:
        return 130


def command_claude(args: argparse.Namespace) -> int:
    paths = _paths(args.config)
    _validate_runtime(paths)
    host, port = _network_settings(args)
    claude = _claude_command()
    proxy = subprocess.Popen(
        _proxy_command(paths, host, port),
        cwd=paths.root,
        env=_proxy_environment(),
    )
    try:
        _wait_until_ready(host, port, proxy, args.timeout)
        child_env = os.environ.copy()
        base_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        model = child_env.get("GATEWAY_MODEL", DEFAULT_MODEL)
        small_model = child_env.get("GATEWAY_SMALL_MODEL", model)
        child_env.update(
            {
                "ANTHROPIC_BASE_URL": f"http://{base_host}:{port}",
                "ANTHROPIC_AUTH_TOKEN": child_env["LITELLM_MASTER_KEY"],
                "ANTHROPIC_MODEL": model,
                "ANTHROPIC_SMALL_FAST_MODEL": small_model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": small_model,
            }
        )
        print(f"Gateway ready. Launching Claude Code with model {model!r}.")
        claude_args = args.claude_args
        if claude_args[:1] == ["--"]:
            claude_args = claude_args[1:]
        return subprocess.run([claude, *claude_args], env=child_env).returncode
    except KeyboardInterrupt:
        return 130
    finally:
        _stop_process(proxy)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-gateway",
        description="Run Claude Code through a local LiteLLM gateway.",
    )
    parser.add_argument("--config", help="LiteLLM YAML file (default: config.yaml)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="save credentials and generate a proxy token")
    setup.add_argument("--force", action="store_true", help="replace existing credentials")
    vscode_choice = setup.add_mutually_exclusive_group()
    vscode_choice.add_argument(
        "--configure-vscode",
        action="store_true",
        help="configure project-local Claude Code settings without prompting",
    )
    vscode_choice.add_argument(
        "--no-configure-vscode",
        action="store_true",
        help="skip Claude Code VS Code settings without prompting",
    )
    setup.set_defaults(handler=command_setup)

    configure = subparsers.add_parser(
        "configure-vscode",
        help="merge project-local or user Claude Code gateway settings",
    )
    configure.add_argument(
        "--scope",
        choices=("local", "user"),
        default="local",
        help="settings scope (default: local to this project)",
    )
    configure.add_argument(
        "--dry-run", action="store_true", help="show the target and values without writing"
    )
    configure.add_argument(
        "--remove", action="store_true", help="remove settings managed by this gateway"
    )
    configure.add_argument("--host", help=f"gateway address (default: {DEFAULT_HOST})")
    configure.add_argument("--port", type=int, help=f"gateway port (default: {DEFAULT_PORT})")
    configure.set_defaults(handler=command_configure_vscode)

    for name, help_text, handler in (
        ("doctor", "validate the local installation", command_doctor),
        ("start", "start only the LiteLLM proxy", command_start),
        ("claude", "start the proxy and launch Claude Code", command_claude),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--host", help=f"listen address (default: {DEFAULT_HOST})")
        command.add_argument("--port", type=int, help=f"listen port (default: {DEFAULT_PORT})")
        command.set_defaults(handler=handler)
        if name == "claude":
            command.add_argument(
                "--timeout", type=float, default=60, help="gateway startup timeout in seconds"
            )
            command.add_argument("claude_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except GatewayError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
