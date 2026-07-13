#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$ROOT_DIR/.venv/bin/claude-gateway" ]]; then
  echo "Error: gateway is not installed. Run ./scripts/setup.sh first." >&2
  exit 1
fi
exec "$ROOT_DIR/.venv/bin/claude-gateway" claude "$@"
