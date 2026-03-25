SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PATH := $(HOME)/.bun/bin:$(PATH)

RUN_DIR := $(ROOT_DIR)/.run
BACKEND_DIR := $(ROOT_DIR)/app/backend
FRONTEND_DIR := $(ROOT_DIR)/app/frontend
COMPOSE_FILE := $(ROOT_DIR)/infra/docker/docker-compose.local.yml

BACKEND_PID := $(RUN_DIR)/backend.pid
WORKER_PID := $(RUN_DIR)/worker.pid
FRONTEND_PID := $(RUN_DIR)/frontend.pid

BACKEND_LOG := $(RUN_DIR)/backend.log
WORKER_LOG := $(RUN_DIR)/worker.log
FRONTEND_LOG := $(RUN_DIR)/frontend.log

DEMO_EMAIL ?= demo@example.com
DEMO_PASSWORD ?= secret123

.PHONY: help check-tools env init run run-backend run-worker run-frontend stop stop-backend stop-worker stop-frontend restart status logs clean infra-up infra-down infra-health backend-sync frontend-sync contracts migrate seed-user demo-seed demo-reset verify

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

check-tools: ## Check required tooling is installed
	@command -v docker >/dev/null || (echo "docker not found" && exit 1)
	@command -v uv >/dev/null || (echo "uv not found" && exit 1)
	@command -v bun >/dev/null || (echo "bun not found (add ~/.bun/bin to PATH)" && exit 1)

env: ## Create local env files from templates if missing
	@test -f "$(BACKEND_DIR)/.env" || cp "$(ROOT_DIR)/infra/env/.env.backend.example" "$(BACKEND_DIR)/.env"
	@test -f "$(FRONTEND_DIR)/.env.local" || cp "$(ROOT_DIR)/infra/env/.env.frontend.example" "$(FRONTEND_DIR)/.env.local"
	@echo "env ready"

backend-sync: ## Install backend dependencies
	@uv --project "$(ROOT_DIR)" sync --all-packages --extra dev

frontend-sync: ## Install frontend dependencies
	@cd "$(FRONTEND_DIR)" && bun install

contracts: ## Generate frontend types from OpenAPI contract
	@cd "$(FRONTEND_DIR)" && bun run gen:contracts

infra-up: ## Start local Postgres + Redis via Docker Compose
	@bash "$(ROOT_DIR)/infra/scripts/bootstrap-local.sh"

infra-down: ## Stop local Postgres + Redis
	@docker compose -f "$(COMPOSE_FILE)" down

infra-health: ## Check infra health (Postgres + Redis)
	@bash "$(ROOT_DIR)/infra/scripts/check-health.sh"

migrate: ## Run backend migrations
	@uv --project "$(ROOT_DIR)" run --package rpml-backend alembic upgrade head

seed-user: ## Create a local demo user for login
	@DEMO_EMAIL="$(DEMO_EMAIL)" DEMO_PASSWORD="$(DEMO_PASSWORD)" uv --project "$(ROOT_DIR)" run --package rpml-backend python -c "import os; from server.infrastructure.auth.password import hash_password; from server.infrastructure.db.models.user import UserORM; from server.infrastructure.db.session import SessionLocal; email=os.environ['DEMO_EMAIL']; password=os.environ['DEMO_PASSWORD']; db=SessionLocal(); user=db.query(UserORM).filter_by(email=email).first(); db.add(UserORM(email=email, hashed_password=hash_password(password))) if user is None else None; db.commit() if user is None else None; print(f'created demo user: {email}' if user is None else f'demo user already exists: {email}'); db.close()"

demo-seed: ## Load idempotent demo scenario (same as POST /api/v1/demo/seed)
	@DEMO_EMAIL="$(DEMO_EMAIL)" uv --project "$(ROOT_DIR)" run --package rpml-backend python -m server.services.demo_seed

demo-reset: demo-seed ## Re-apply demo seed (idempotent alias)

init: check-tools env backend-sync frontend-sync contracts infra-up migrate seed-user demo-seed infra-health ## Full local bootstrap (deps + infra + migrations + demo user + scenario seed)
	@echo "init complete"

run-backend: ## Start backend API in background (uvicorn)
	@bash -c 'set -euo pipefail; mkdir -p "$(RUN_DIR)"; \
	if [[ -f "$(BACKEND_PID)" ]] && kill -0 "$$(cat "$(BACKEND_PID)")" 2>/dev/null; then \
		echo "backend already running (pid=$$(cat "$(BACKEND_PID)"))"; \
	else \
		cd "$(BACKEND_DIR)" && nohup uv --project "$(ROOT_DIR)" run --package rpml-backend uvicorn server.main:app --host 0.0.0.0 --port 8000 > "$(BACKEND_LOG)" 2>&1 & echo $$! > "$(BACKEND_PID)"; \
		echo "backend started (pid=$$(cat "$(BACKEND_PID)"))"; \
	fi'

run-worker: ## Start Celery worker in background
	@bash -c 'set -euo pipefail; mkdir -p "$(RUN_DIR)"; \
	if [[ -f "$(WORKER_PID)" ]] && kill -0 "$$(cat "$(WORKER_PID)")" 2>/dev/null; then \
		echo "worker already running (pid=$$(cat "$(WORKER_PID)"))"; \
	else \
		cd "$(BACKEND_DIR)" && nohup uv --project "$(ROOT_DIR)" run --package rpml-backend celery -A server.infrastructure.queue.celery_app:celery_app worker -l info > "$(WORKER_LOG)" 2>&1 & echo $$! > "$(WORKER_PID)"; \
		echo "worker started (pid=$$(cat "$(WORKER_PID)"))"; \
	fi'

run-frontend: ## Start frontend dev server in background
	@bash -c 'set -euo pipefail; mkdir -p "$(RUN_DIR)"; \
	if [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" 2>/dev/null; then \
		echo "frontend already running (pid=$$(cat "$(FRONTEND_PID)"))"; \
	else \
		cd "$(FRONTEND_DIR)"; nohup bun --bun run dev > "$(FRONTEND_LOG)" 2>&1 & echo $$! > "$(FRONTEND_PID)"; \
		echo "frontend started (pid=$$(cat "$(FRONTEND_PID)"))"; \
	fi'

run: infra-up run-backend run-worker run-frontend status ## Start all local services
	@echo "run complete"

stop-backend: ## Stop backend API process
	@bash -c 'set -euo pipefail; \
	if [[ -f "$(BACKEND_PID)" ]] && kill -0 "$$(cat "$(BACKEND_PID)")" 2>/dev/null; then \
		kill "$$(cat "$(BACKEND_PID)")" && rm -f "$(BACKEND_PID)"; echo "backend stopped"; \
	else \
		rm -f "$(BACKEND_PID)"; echo "backend not running"; \
	fi'

stop-worker: ## Stop Celery worker process
	@bash -c 'set -euo pipefail; \
	if [[ -f "$(WORKER_PID)" ]] && kill -0 "$$(cat "$(WORKER_PID)")" 2>/dev/null; then \
		kill "$$(cat "$(WORKER_PID)")" && rm -f "$(WORKER_PID)"; echo "worker stopped"; \
	else \
		rm -f "$(WORKER_PID)"; echo "worker not running"; \
	fi'

stop-frontend: ## Stop frontend dev server process
	@bash -c 'set -euo pipefail; \
	if [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" 2>/dev/null; then \
		kill "$$(cat "$(FRONTEND_PID)")" && rm -f "$(FRONTEND_PID)"; echo "frontend stopped"; \
	else \
		rm -f "$(FRONTEND_PID)"; echo "frontend not running"; \
	fi'

stop: stop-frontend stop-worker stop-backend infra-down ## Stop all local services
	@echo "stop complete"

restart: stop run ## Restart all local services

status: ## Show status of docker services and app processes
	@echo "== Docker =="
	@docker compose -f "$(COMPOSE_FILE)" ps
	@echo ""
	@echo "== App processes =="
	@bash -c 'for name in backend worker frontend; do \
		pid_file="$(RUN_DIR)/$$name.pid"; \
		if [[ -f "$$pid_file" ]] && kill -0 "$$(cat "$$pid_file")" 2>/dev/null; then \
			echo "$$name: running (pid=$$(cat "$$pid_file"))"; \
		else \
			echo "$$name: stopped"; \
		fi; \
	done'

logs: ## Tail backend, worker and frontend logs
	@mkdir -p "$(RUN_DIR)"
	@touch "$(BACKEND_LOG)" "$(WORKER_LOG)" "$(FRONTEND_LOG)"
	@tail -f "$(BACKEND_LOG)" "$(WORKER_LOG)" "$(FRONTEND_LOG)"

verify: ## Run full verification gate
	@bash "$(ROOT_DIR)/infra/scripts/verify-all.sh"

clean: ## Remove runtime PID/log files
	@rm -rf "$(RUN_DIR)"
	@echo "cleaned $(RUN_DIR)"
