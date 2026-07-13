# Contributing

Thank you for improving the gateway. Small, focused changes with tests and clear user impact are
the easiest to review.

## Before opening an issue

1. Read the README troubleshooting section.
2. Update the project and run `claude-gateway doctor`.
3. Search existing issues.
4. Remove API keys, proxy tokens, prompts, source code, account IDs, and endpoint credentials from
   all output.

Use GitHub Discussions or a feature request for design questions. Follow `SECURITY.md` instead of
a public issue for vulnerabilities or suspected credential exposure.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --editable ".[dev]"
pre-commit install
```

Run the same checks as CI:

```bash
ruff check .
ruff format --check .
pytest --cov=claude_code_gateway --cov-report=term-missing
```

To apply formatting locally:

```bash
ruff check --fix .
ruff format .
```

## Pull requests

- Keep one behavioral change per pull request.
- Add or update tests for launcher behavior and failure messages.
- Update README, configuration, or provider docs when users must act differently.
- Add a concise entry under `CHANGELOG.md` → Unreleased.
- Do not make live paid API calls in tests or CI.
- Do not add a dependency when the standard library or an existing dependency is adequate.

The project supports Python 3.10+ on Windows, macOS, and Linux. Avoid shell-specific behavior in
the Python implementation; wrappers should only bootstrap or invoke it.

## Adding a provider example

Read `docs/providers.md`. Use placeholders rather than an account's real model deployment or
endpoint. Link to primary provider and LiteLLM documentation, document required environment
variables, and manually verify streaming and tool use before claiming compatibility.

## Commit style

Use an imperative subject that says what changes, for example:

```text
Validate configured model aliases before launch
```

Signing commits is welcome but not required unless repository policy says otherwise.

Maintainers should follow [the release checklist](docs/releasing.md) when publishing a version.
