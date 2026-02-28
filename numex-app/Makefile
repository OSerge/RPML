# NUMEX dev Makefile — запуск Supabase, backend, redis, опционально vllm
# Использование: make run-dev | stop | logs | migrate

COMPOSE      := docker compose
SUPABASE_DIR := supabase
SUPABASE_CMD := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev-db.yml --env-file .env

.PHONY: run-dev run-dev-full stop down logs logs-backend migrate migrate-current help

help:
	@echo "NUMEX dev"
	@echo ""
	@echo "  make run-dev        — Supabase + backend + redis (основной dev)"
	@echo "  make run-dev-full   — run-dev + vllm (для чата/объяснений)"
	@echo "  make stop           — остановить backend/redis и Supabase"
	@echo "  make down           — stop + удалить контейнеры"
	@echo "  make logs           — логи всех сервисов"
	@echo "  make logs-backend   — логи только backend"
	@echo "  make migrate        — alembic upgrade head (backend)"
	@echo "  make migrate-current — показать текущую версию миграций"
	@echo ""

run-dev:
	@echo "Starting Supabase (DB on :54322)..."
	@cd $(SUPABASE_DIR) && $(SUPABASE_CMD) up -d
	@echo "Starting backend + redis..."
	@$(COMPOSE) up -d
	@echo "Done. Backend: http://localhost:8001, Supabase: http://localhost:8000, DB: localhost:54322"

run-dev-full: run-dev
	@echo "Starting vllm-server (GPU)..."
	@$(COMPOSE) -f docker-compose.local.yml up -d vllm-server
	@echo "vllm: http://localhost:8001 (inside host, backend uses host.docker.internal:8001)"

stop:
	@$(COMPOSE) down 2>/dev/null || true
	@$(COMPOSE) -f docker-compose.local.yml down 2>/dev/null || true
	@cd $(SUPABASE_DIR) && $(SUPABASE_CMD) down 2>/dev/null || true
	@echo "Stopped."

down: stop

logs:
	@$(COMPOSE) logs -f

logs-backend:
	@$(COMPOSE) logs -f backend

migrate:
	@cd backend && uv run alembic upgrade head

migrate-current:
	@cd backend && uv run alembic current
