# Repository design decisions

This document explains the repository's structure and the benefits and trade-offs behind its key
technical decisions.

## Repository structure

```text
.
├── .github/
│   ├── ISSUE_TEMPLATE/        # Structured, secret-safe bug and feature reports
│   ├── workflows/ci.yml       # Cross-platform tests and quality checks
│   ├── dependabot.yml         # Scheduled dependency update proposals
│   └── pull_request_template.md
├── docs/
│   ├── images/                # README assets
│   ├── configuration.md       # Complete configuration reference
│   ├── providers.md           # Provider extension workflow
│   ├── releasing.md           # Maintainer release checklist
│   └── repository-review.md   # Decisions and trade-offs
├── examples/providers/        # Standalone provider configuration starting points
├── scripts/                   # Thin setup and launch wrappers for Bash/PowerShell
├── src/claude_code_gateway/   # Tested cross-platform implementation
├── tests/                     # Offline unit tests; no paid API traffic
├── .editorconfig              # Consistent basic editor behavior
├── .env.example               # Safe variable template with no credentials
├── .gitattributes             # Stable line endings and binary classification
├── .gitignore                 # Secrets, environments, caches, logs, local state
├── .pre-commit-config.yaml    # Fast contributor checks and private-key detection
├── CHANGELOG.md               # User-visible release history
├── CODE_OF_CONDUCT.md         # Community expectations
├── CONTRIBUTING.md            # Contributor workflow
├── LICENSE                    # MIT reuse terms
├── README.md                  # User onboarding and operations guide
├── SECURITY.md                # Private reporting and trust boundary
├── config.yaml                # Minimal default LiteLLM route
├── pyproject.toml             # Package, dependencies, CLI, and tool settings
└── requirements.txt           # Familiar compatibility install path
```

## Setup option evaluation

| Option | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Repeated shell exports | No files | Error-prone, session-local, platform-specific | Rejected |
| `.env` only | Simple and cross-platform | Users must create syntax correctly; weak key can be reused | Used as storage, not the whole UX |
| Bash and PowerShell implementations | Familiar per platform | Logic drifts and doubles tests | Wrappers only |
| Interactive Python wizard | Hidden input, validation, generated proxy token, one behavior everywhere | Requires dependencies installed first | Selected |
| OS keychain | Stronger secret storage | Additional dependencies and inconsistent headless/WSL behavior | Deferred; recommended for shared deployments |
| Docker Compose | Reproducible service runtime | Docker is heavy for a one-user localhost tool and complicates host Claude integration | Not included by default |

The selected flow is: platform setup wrapper creates `.venv` and installs the project; the wizard
saves the key once; the combined launcher starts and stops both processes. This is the smallest
design that meets the one-command daily workflow without hiding significant system changes.

## File-by-file rationale and trade-offs

- `src/claude_code_gateway/cli.py` centralizes validation and process management. It adds a
  small maintained code surface, but eliminates divergent platform behavior and makes failures
  testable.
- `config.yaml` remains minimal. This avoids inventing an abstraction over LiteLLM; users must
  still learn LiteLLM syntax when adding advanced providers.
- `.env.example` documents local inputs without a usable secret. `.env` is convenient for a
  single user but is not a production secret manager.
- `scripts/*.sh` and `scripts/*.ps1` avoid virtual-environment activation and make onboarding
  memorable. Four tiny wrappers are some duplication, but they contain no business logic.
- `pyproject.toml` is the canonical Python definition. `requirements.txt` duplicates runtime
  versions only for users and automation expecting it; Dependabot and review must keep them in
  sync.
- `examples/providers/` makes extension copyable without bloating the default. Placeholder model
  IDs avoid rapidly stale recommendations, at the cost of one provider-doc lookup.
- `README.md` carries the full happy path and common operations. Deeper references live under
  `docs/` so the landing page stays navigable.
- `pytest`, Ruff, pre-commit, and one CI workflow cover high-value errors with little configuration.
  Heavier type checking, release automation, containers, databases, and observability were not
  added because the current code and local-only scope do not justify them.
- `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and issue templates make reuse
  and participation expectations explicit. The MIT license favors adoption but provides no
  copyleft requirement or warranty.

## Security review

Implemented controls:

- provider and proxy credentials resolve only from environment variables;
- `.env`, local configs, logs, databases, environments, and editor state are ignored;
- hidden key input and diagnostic redaction prevent routine terminal disclosure;
- a cryptographically random proxy token replaces the shared static value;
- default binding is loopback and diagnostics warn on network exposure;
- launcher telemetry is disabled and no detailed logging/callback is enabled;
- pre-commit detects common private keys and issue templates warn against sensitive output;
- GitHub Actions has read-only repository content permission.

Residual risks:

- `.env` is plaintext to the local user and any process with equivalent permissions;
- prompts and source leave the machine for a hosted provider;
- a local bearer token over HTTP is insufficient for non-loopback use;
- LiteLLM and provider dependencies form a substantial third-party supply chain;
- `drop_params: true` can silently remove unsupported behavior;
- no test can guarantee model behavior or provider data policy.

For a multi-user deployment, replace `.env` with managed secrets, terminate TLS, isolate the
service account and network, create scoped/rotated client keys, configure budgets and rate limits,
define log retention, and monitor upstream security releases.

## Maintenance and extension policy

Add complexity only after a concrete need:

- Add a provider with YAML and documentation first; change Python only when lifecycle behavior is
  genuinely provider-independent.
- Keep default routes stable and generally available; do not silently move users to previews.
- Pin direct runtime dependencies and upgrade through reviewed pull requests with cross-platform
  CI.
- Keep tests offline. Live provider smoke tests are opt-in maintainer checks because they cost
  money, require secrets, and can leak prompts.
- Treat any change to binding, authentication, logging, or secret precedence as security-sensitive
  and document it in the changelog.
