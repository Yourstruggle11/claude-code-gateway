from __future__ import annotations

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from claude_code_gateway import cli


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        """model_list:
  - model_name: test-model
    litellm_params:
      model: gemini/test-model
      api_key: os.environ/GEMINI_API_KEY
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_project_root", lambda: tmp_path)
    for key in (
        "GEMINI_API_KEY",
        "LITELLM_MASTER_KEY",
        "GATEWAY_MODEL",
        "GATEWAY_SMALL_MODEL",
        "GATEWAY_CONFIG",
    ):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def test_upsert_env_preserves_comments_and_unrelated_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# local settings\nOTHER=value\nGEMINI_API_KEY=old\n", encoding="utf-8")

    cli._upsert_env(env_file, {"GEMINI_API_KEY": "new", "LITELLM_MASTER_KEY": "secret"})

    assert env_file.read_text(encoding="utf-8") == (
        "# local settings\nOTHER=value\nGEMINI_API_KEY=new\n\nLITELLM_MASTER_KEY=secret\n"
    )


def test_validate_runtime_accepts_valid_configuration(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / ".env").write_text(
        "GEMINI_API_KEY=gemini-secret\nLITELLM_MASTER_KEY=sk-local-abcdefghijklmnopqrstuvwxyz\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GATEWAY_MODEL", "test-model")
    monkeypatch.setenv("GATEWAY_SMALL_MODEL", "test-model")

    config = cli._validate_runtime(cli._paths())

    assert cli._model_aliases(config) == {"test-model"}
    assert os.environ["GEMINI_API_KEY"] == "gemini-secret"


def test_validate_runtime_rejects_unknown_model(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / ".env").write_text(
        "GEMINI_API_KEY=gemini-secret\nLITELLM_MASTER_KEY=sk-local-abcdefghijklmnopqrstuvwxyz\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GATEWAY_MODEL", "missing-model")

    with pytest.raises(cli.GatewayError, match="not in model_list"):
        cli._validate_runtime(cli._paths())


def test_validate_runtime_uses_provider_variables_from_config(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "config.yaml").write_text(
        """model_list:
  - model_name: test-model
    litellm_params:
      model: openai/test-model
      api_key: os.environ/OPENAI_API_KEY
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
""",
        encoding="utf-8",
    )
    (project / ".env").write_text(
        "OPENAI_API_KEY=openai-secret\nLITELLM_MASTER_KEY=sk-local-abcdefghijklmnopqrstuvwxyz\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GATEWAY_MODEL", "test-model")
    monkeypatch.setenv("GATEWAY_SMALL_MODEL", "test-model")

    config = cli._validate_runtime(cli._paths())

    assert cli._model_aliases(config) == {"test-model"}
    assert os.environ["OPENAI_API_KEY"] == "openai-secret"


def test_setup_reuses_api_key_and_generates_proxy_key(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / ".env").write_text("GEMINI_API_KEY=existing-key\n", encoding="utf-8")
    monkeypatch.setattr(cli.secrets, "token_urlsafe", lambda _length: "generated-token")
    args = argparse.Namespace(config=None, force=False)

    assert cli.command_setup(args) == 0

    values = (project / ".env").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=existing-key" in values
    assert "LITELLM_MASTER_KEY=sk-local-generated-token" in values


def test_setup_can_configure_vscode_noninteractively(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / ".env").write_text("GEMINI_API_KEY=existing-key\n", encoding="utf-8")
    configured: list[argparse.Namespace] = []
    monkeypatch.setattr(cli, "command_configure_vscode", configured.append)
    args = argparse.Namespace(
        config=None,
        force=False,
        configure_vscode=True,
        no_configure_vscode=False,
    )

    assert cli.command_setup(args) == 0

    assert len(configured) == 1
    assert configured[0].scope == "local"
    assert configured[0].dry_run is False


def _vscode_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "config": None,
        "scope": "local",
        "dry_run": False,
        "remove": False,
        "host": None,
        "port": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_configure_vscode_preserves_settings_and_creates_backup(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_valid_env(project)
    settings_path = project / ".claude" / "settings.local.json"
    settings_path.parent.mkdir()
    original = {
        "permissions": {"allow": ["Read"]},
        "env": {"KEEP_ME": "yes"},
    }
    settings_path.write_text(cli.json.dumps(original), encoding="utf-8")

    assert cli.command_configure_vscode(_vscode_args()) == 0

    settings = cli.json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["permissions"] == original["permissions"]
    assert settings["env"]["KEEP_ME"] == "yes"
    assert settings["env"]["ANTHROPIC_AUTH_TOKEN"].startswith("sk-local-")
    assert settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "test-model"
    assert settings["env"]["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] == "1"
    assert settings["model"] == "test-model"
    assert (
        cli.json.loads(
            settings_path.with_name("settings.local.json.bak").read_text(encoding="utf-8")
        )
        == original
    )
    assert "sk-local-abcdefghijklmnopqrstuvwxyz" not in capsys.readouterr().out


def test_configure_vscode_is_idempotent(project: Path) -> None:
    _write_valid_env(project)
    args = _vscode_args()

    assert cli.command_configure_vscode(args) == 0
    settings_path = project / ".claude" / "settings.local.json"
    first_content = settings_path.read_text(encoding="utf-8")
    assert cli.command_configure_vscode(args) == 0

    assert settings_path.read_text(encoding="utf-8") == first_content
    assert not settings_path.with_name("settings.local.json.bak").exists()


def test_configure_vscode_dry_run_redacts_token(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_valid_env(project)

    assert cli.command_configure_vscode(_vscode_args(dry_run=True)) == 0

    output = capsys.readouterr().out
    assert "Authentication token: [hidden]" in output
    assert "sk-local-abcdefghijklmnopqrstuvwxyz" not in output
    assert not (project / ".claude" / "settings.local.json").exists()


def test_configure_vscode_remove_keeps_unrelated_settings(project: Path) -> None:
    _write_valid_env(project)
    args = _vscode_args()
    assert cli.command_configure_vscode(args) == 0
    settings_path = project / ".claude" / "settings.local.json"
    settings = cli.json.loads(settings_path.read_text(encoding="utf-8"))
    settings["env"]["KEEP_ME"] = "yes"
    settings["permissions"] = {"allow": ["Read"]}
    settings_path.write_text(cli.json.dumps(settings), encoding="utf-8")

    assert cli.command_configure_vscode(_vscode_args(remove=True)) == 0

    removed = cli.json.loads(settings_path.read_text(encoding="utf-8"))
    assert removed["env"] == {"KEEP_ME": "yes"}
    assert removed["permissions"] == {"allow": ["Read"]}
    assert "model" not in removed


def test_configure_vscode_rejects_invalid_existing_json(project: Path) -> None:
    _write_valid_env(project)
    settings_path = project / ".claude" / "settings.local.json"
    settings_path.parent.mkdir()
    settings_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(cli.GatewayError, match="Could not read Claude Code settings"):
        cli.command_configure_vscode(_vscode_args())


@pytest.mark.parametrize("port", [0, 65536, "not-a-number"])
def test_network_settings_rejects_invalid_ports(port: object) -> None:
    args = argparse.Namespace(host="127.0.0.1", port=port)

    with pytest.raises(cli.GatewayError, match="port"):
        cli._network_settings(args)


def test_main_prints_actionable_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor", "--port", "0"]) == 1
    assert "Error:" in capsys.readouterr().err


def _write_valid_env(project: Path) -> None:
    (project / ".env").write_text(
        "GEMINI_API_KEY=gemini-secret\n"
        "LITELLM_MASTER_KEY=sk-local-abcdefghijklmnopqrstuvwxyz\n"
        "GATEWAY_MODEL=test-model\n"
        "GATEWAY_SMALL_MODEL=test-model\n",
        encoding="utf-8",
    )


def test_doctor_reports_runtime_and_claude(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_valid_env(project)
    monkeypatch.setattr(cli, "_litellm_command", lambda: "litellm-test")
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/{name}")
    args = argparse.Namespace(config=None, host="127.0.0.1", port=4000)

    assert cli.command_doctor(args) == 0

    output = capsys.readouterr().out
    assert "[OK] Models: test-model" in output
    assert "[OK] Claude Code: /claude" in output
    assert "Doctor completed successfully." in output


def test_start_propagates_proxy_exit_code(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_valid_env(project)
    monkeypatch.setattr(cli, "_proxy_command", lambda *_args: ["fake-litellm"])
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=17),
    )
    args = argparse.Namespace(config=None, host="127.0.0.1", port=4000)

    assert cli.command_start(args) == 17


def test_proxy_environment_removes_generic_debug_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG", "release")
    monkeypatch.setenv("DETAILED_DEBUG", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "preserved")

    environment = cli._proxy_environment()

    assert "DEBUG" not in environment
    assert "DETAILED_DEBUG" not in environment
    assert environment["GEMINI_API_KEY"] == "preserved"
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"


def test_claude_injects_gateway_environment_and_stops_proxy(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_valid_env(project)
    monkeypatch.setattr(cli, "_proxy_command", lambda *_args: ["fake-litellm"])
    monkeypatch.setattr(cli, "_claude_command", lambda: "fake-claude")
    proxy = SimpleNamespace()
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: proxy)
    monkeypatch.setattr(cli, "_wait_until_ready", lambda *_args: None)
    stopped: list[object] = []
    monkeypatch.setattr(cli, "_stop_process", stopped.append)
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    args = argparse.Namespace(
        config=None,
        host="127.0.0.1",
        port=4000,
        timeout=1,
        claude_args=["--", "--print", "hello"],
    )

    assert cli.command_claude(args) == 0

    assert captured["command"] == ["fake-claude", "--print", "hello"]
    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert child_env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4000"
    assert child_env["ANTHROPIC_AUTH_TOKEN"].startswith("sk-local-")
    assert child_env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "test-model"
    assert stopped == [proxy]


def test_read_config_rejects_invalid_yaml(tmp_path: Path) -> None:
    config = tmp_path / "broken.yaml"
    config.write_text("model_list: [", encoding="utf-8")

    with pytest.raises(cli.GatewayError, match="Could not read"):
        cli._read_config(config)


def test_stop_process_terminates_then_kills_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: int) -> None:
            events.append(f"wait-{timeout}")
            if timeout == 10:
                raise cli.subprocess.TimeoutExpired("proxy", timeout)

        def kill(self) -> None:
            events.append("kill")

    cli._stop_process(FakeProcess())

    assert events == ["terminate", "wait-10", "kill", "wait-5"]
