#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Error: Python 3.10 or newer was not found." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi

.venv/bin/python -c 'import sys; print(f"Using Python {sys.version.split()[0]}"); sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Error: .venv uses Python older than 3.10. Remove .venv and rerun setup with a newer Python." >&2
  exit 1
}

.venv/bin/python -m pip install --editable .
.venv/bin/claude-gateway setup
