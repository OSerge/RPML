# FinTech App - Personal Finance с RPML

Сервис оптимизации выплат по долгам с MILP-алгоритмом и AI-объяснениями.

## Supabase (рекомендуется)

Авторизация, PostgreSQL и pgvector для RAG из коробки.

1. Создайте проект на [supabase.com](https://supabase.com).
2. В настройках проекта (Settings → API): скопируйте **Project URL**, **anon public** и **JWT Secret**.
3. В БД включите pgvector: в SQL Editor выполните `CREATE EXTENSION IF NOT EXISTS vector;`.
4. **Backend** — в `backend/.env`:
   - `DATABASE_URL` и `DATABASE_URL_SYNC` — connection string из Settings → Database (URI, режим Session).
   - `SUPABASE_JWT_SECRET` — JWT Secret из Settings → API.
5. **Frontend** — в `frontend/.env`:
   - `VITE_SUPABASE_URL` — Project URL.
   - `VITE_SUPABASE_ANON_KEY` — anon public key.
6. Миграции: `cd backend && uv run alembic upgrade head`.
7. Индексация RAG (один раз): из Python `from rag.indexer import index_knowledge_base; index_knowledge_base()`.

После этого регистрация и вход идут через Supabase, без своего auth-бэкенда.

## Структура

- `backend/` - FastAPI, RPML, RAG (pgvector), Celery
- `frontend/` - React, Vite, Tailwind, Supabase Auth
- `vllm-server/` - профили запуска LLM (vLLM)
- `supabase/` - полный self-hosted Supabase (официальный Docker: PostgreSQL, pgvector, Kong, Auth, PostgREST, Studio и др.), см. [supabase/README.md](supabase/README.md)

## Локальная разработка

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

При использовании Supabase достаточно указать в `.env` строку подключения к БД и JWT Secret. Иначе поднимите PostgreSQL и Redis (например, через Docker).

### Frontend

```bash
cd frontend
bun install   # или npm install
bun run --bun dev   # или npm run dev
```

В `.env` задайте `VITE_SUPABASE_URL` и `VITE_SUPABASE_ANON_KEY` (см. выше).

### vLLM (опционально, для AI-объяснений)

```bash
cd vllm-server
./local.sh   # RTX 3060: Qwen2.5-3B
```

## Docker

### Режим «быстрый старт» (свой Postgres + GoTrue)

В одном compose: Postgres (pgvector), GoTrue (Supabase Auth), backend, frontend, Redis, Celery, vLLM.

1. В каталоге `fintech-app` скопируйте `.env.example` в `.env`.
2. Задайте `SUPABASE_JWT_SECRET` (не менее 32 символов).
3. Сгенерируйте anon key (JWT с payload `{"role":"anon","iss":"supabase"}` и тем же секретом) и укажите в `VITE_SUPABASE_ANON_KEY`. Можно использовать [jwt.io](https://jwt.io) или:  
   `python -c "import jwt; print(jwt.encode({'role':'anon','iss':'supabase'}, 'ВАШ_SUPABASE_JWT_SECRET', algorithm='HS256'))"` (пакет `pyjwt`).
4. Запуск:
```bash
cd fintech-app
docker compose up -d
```
5. После первого запуска: миграции и RAG (один раз):
```bash
docker compose exec backend uv run alembic upgrade head
docker compose exec backend uv run python -c "from rag.indexer import index_knowledge_base; print(index_knowledge_base())"
```
Фронт: http://localhost:3000.

### Режим «полный self-hosted Supabase»

Используется полный экземпляр Supabase по [официальной документации](https://supabase.com/docs/guides/self-hosting/docker) (PostgreSQL, pgvector, Kong, Auth, PostgREST, Realtime, Storage, Studio).

1. Установите и запустите Supabase из каталога `supabase/` — см. [supabase/README.md](supabase/README.md).
2. В корне `fintech-app` в `.env` задайте переменные для подключения к этому Supabase (в т.ч. `SUPABASE_POSTGRES_PASSWORD`, `SUPABASE_POOLER_TENANT_ID`, `SUPABASE_JWT_SECRET`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` — см. комментарии в `docker-compose.supabase-external.yml`).
3. Запуск приложения:
```bash
docker compose -f docker-compose.yml -f docker-compose.supabase-external.yml up -d
```
В этом режиме свои контейнеры Postgres и GoTrue не поднимаются; backend и frontend подключаются к БД и Kong запущенного Supabase.

Локальная разработка с маленькой моделью (любой режим):
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up
```

## API

- GET `/api/v1/auth/me` — текущий пользователь (по JWT Supabase или legacy).
- POST `/api/v1/auth/register` — только без Supabase.
- POST `/api/v1/auth/login` — только без Supabase.
- GET/POST `/api/v1/debts` — долги
- POST `/api/v1/optimize` — запуск оптимизации
- POST `/api/v1/explain` — AI объяснение
- GET `/api/v1/budget/summary` — сводка бюджета
