#!/usr/bin/env bash
# Verification gate: core, root, backend, frontend tests + frontend build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v bun >/dev/null 2>&1; then
  echo "verify-all: bun not found in PATH (add ~/.bun/bin or install Bun)." >&2
  exit 1
fi

echo "==> core/rpml tests"
uv --project "$ROOT" run --all-packages --extra dev pytest core/rpml/tests -q

echo "==> root tests"
uv --project "$ROOT" run --all-packages --extra dev pytest tests -q

echo "==> app/backend tests"
uv --project "$ROOT" run --all-packages --extra dev pytest app/backend/tests -q

echo "==> app/frontend bun test"
( cd app/frontend && bun test )

echo "==> app/frontend build:check"
( cd app/frontend && bun run build:check )

echo "verify-all: OK"
