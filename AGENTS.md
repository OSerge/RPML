# AGENTS Instructions

This file is the primary guide for AI agents working in this repository.
Use it before touching files, running commands, or proposing changes.

## 1) Scope and project layout

This is a monorepo with three main parts:

- `core/rpml`: optimization core library (MILP, baseline strategies, experiment CLI).
- `app/backend`: FastAPI API, PostgreSQL models, Alembic migrations, Celery async tasks.
- `app/frontend`: React + Vite UI.
- `shared/contracts`: OpenAPI snapshot used for contract checks.
- `infra`: docker-compose, env templates, local bootstrap scripts.
- `tests`: repository-level smoke tests.

## 2) Operating principles

- Keep changes **small and incremental**.
- Always update contract + implementation + tests in the same flow.
- If a file was already edited in this session, do not revert it unless explicitly requested.
- Prefer deterministic, reproducible commands.
- Prefer safety over speed for DB and async behavior.
- Do not skip verification steps if code or behavior changed.

## 3) Must-know files

- Core:
  - `core/rpml/src/rpml` (library code)
  - `core/rpml/src/rpml/cli.py` (experiment runner)
- Backend:
  - `app/backend/src/server/main.py`
  - `app/backend/src/server/api/v1` (routes)
  - `app/backend/src/server/application` (use-cases)
  - `app/backend/src/server/domain/models` (schemas)
  - `app/backend/src/server/infrastructure` (DB, auth, repositories, queue)
  - `app/backend/src/server/infrastructure/db/models` (ORM models)
  - `app/backend/alembic` (migrations)
  - `app/backend/tests`
- Frontend:
  - `app/frontend/src/lib/api-client.ts`
  - `app/frontend/src/App.tsx`
  - `app/frontend/src/main.tsx`
  - `app/frontend/tests`
- Contracts:
  - `shared/contracts/openapi/rpml-web-app.v1.yaml`

## 4) Environment setup

Required tools:

- `docker`, `uv`, `bun`

Before backend/frontend work:

1. `make check-tools`
2. `make env`
3. Ensure files exist:
   - `app/backend/.env`
   - `app/frontend/.env.local`

Important env variables:

- Backend: `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `JWT_SECRET_KEY`, `DEBUG`
- Frontend: `VITE_API_BASE_URL`

## 5) Core commands (run from repo root)

### Initialization and run

- `make init`
- `make run`
- `make status`
- `make stop`

### Dependency and infra management

- `make backend-sync`
- `make frontend-sync`
- `make contracts`
- `make infra-up`
- `make infra-down`
- `make infra-health`
- `make migrate`

### Service entrypoints

- Backend API:
  - `uv --project . run --package rpml-backend uvicorn server.main:app --host 0.0.0.0 --port 8000`
- Celery worker:
  - `uv --project . run --package rpml-backend celery -A server.infrastructure.queue.celery_app:celery_app worker -l info`
- Frontend:
  - `cd app/frontend && bun --bun run dev`

### Experiment run (core)

- `uv run run-experiments`
- Useful pattern: `uv run run-experiments -n 4 8 -m 3 -t 60`

## 6) Test and quality gates

Use this sequence after changes:

1. `make verify`
2. `cd app/frontend && bun test`
3. `cd app/frontend && bun run build:check`

Targeted checks:

- `uv --project . run --all-packages --extra dev pytest core/rpml/tests -q`
- `uv --project . run --all-packages --extra dev pytest app/backend/tests -q`
- `uv --project . run --all-packages --extra dev pytest tests -q`

## 7) API contract workflow

If you change any request/response shape, route behavior, or status code:

1. Update backend implementation and models.
2. Ensure OpenAPI aligns with expected contract.
3. Keep `shared/contracts/openapi/rpml-web-app.v1.yaml` in sync.
4. Run `make contracts`.
5. Update frontend usage/type assumptions if needed.
6. Run checks from section 6.

## 8) Change workflow by layer

### Core (`core/rpml`)

- Update implementation, then add/adjust tests in `core/rpml/tests`.
- Keep computational changes minimal and deterministic.

### Backend (`app/backend`)

- Model/schema change → use-case change → API route change → migration if needed.
- Always consider repository-level behavior and DB constraints.
- For async tasks: ensure task status transitions are explicit and persisted.

### Frontend (`app/frontend`)

- Update API client types first, then page/component logic.
- Keep token handling and auth flow consistent with `api-client.ts`.
- Add/update tests in `app/frontend/tests` for changed user-facing behavior.

### DB/Migrations

- All schema changes go through Alembic migration files in `app/backend/alembic/versions`.
- Never patch database tables directly.

## 9) Fast triage playbook (for failures)

- API down: check `make status`, then `infra-health`, then `/health` endpoint.
- `401` issues: inspect token flow (`app/frontend/src/lib/auth-storage.ts`, `api-client.ts`, `get_current_user`).
- Async optimization stuck on `pending`: verify Redis and worker process are running.
- Contract mismatch: compare snapshot test in `app/backend/tests/test_openapi_contract.py` and run `make contracts`.
- Seed/demo issues: inspect `app/backend/services/demo_seed.py` and ensure payload shape matches expectations.

## 10) Do / Don’t

### Do

- Do update docs and tests for behavior changes.
- Do keep changes scoped and reversible.
- Do validate with `make verify` before handoff.
- Do include user-facing impacts in PR notes.

### Don’t

- Don’t edit generated files manually unless intended.
- Don’t add API changes without contract sync.
- Don’t skip task status checks for async endpoints.
- Don’t modify `.env` secrets in repo history without rotating and documenting.

## 11) Good agent habits

- State assumptions clearly when user intent is ambiguous.
- Prefer direct commands over indirect workarounds.
- Keep edits in one conceptual pass after first context pass.
- If uncertain about required command scope, ask one clarifying question before action.
