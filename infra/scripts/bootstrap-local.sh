#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

docker compose -f infra/docker/docker-compose.local.yml up -d

echo "Stack: postgres (5432), redis (6379)."
echo "Backend: copy infra/env/.env.backend.example to app/backend/.env"
echo "Frontend: copy infra/env/.env.frontend.example to app/frontend/.env.local"
