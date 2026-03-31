#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f infra/docker/docker-compose.local.yml)

"${COMPOSE[@]}" ps
"${COMPOSE[@]}" exec -T postgres pg_isready -U rpml -d rpml
"${COMPOSE[@]}" exec -T redis redis-cli ping

if [[ "${BACKEND_HEALTH_URL:-}" != "" ]]; then
  curl -fsS --max-time 10 -o /dev/null "${BACKEND_HEALTH_URL}"
fi
