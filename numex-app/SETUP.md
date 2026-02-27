# Быстрый старт NUMEX

## Что уже настроено:

1. **Supabase Auth** (порт 8000 через Kong):
   - Создан пользователь: `test@numex.app` / `Test123456`
   - JWT токены настроены для авторизации
   - База данных: supabase-db (порт 5432)

2. **Backend API** (порт 8001):
   - Подключён к собственному PostgreSQL с pgvector (порт 5433)
   - Миграции применены
   - Тестовые долги добавлены (3 долга)
   - JWT валидация настроена (verify_aud отключена для совместимости)
   - Автоматическое создание пользователя из JWT токена

3. **Frontend** (порт 3000):
   - Страница логина через Supabase Auth
   - Защищённые роуты (ProtectedRoute)
   - Прокси на backend (localhost:8001)
   - Кнопка выхода в хедере

## Запуск:

### 1. Проверьте, что Supabase запущен:
```bash
docker ps | grep supabase
# Должны быть запущены: supabase-db, supabase-kong, supabase-auth и др.
```

Если не запущен:
```bash
cd supabase && docker compose up -d
```

### 2. Проверьте backend:
```bash
cd numex-app
docker compose ps backend
# Должен быть: Up

curl http://localhost:8001/api/v1/debts
# Ответ: {"detail":"Not authenticated"} - это правильно!
```

Если не запущен:
```bash
docker compose up -d postgres redis backend
```

### 3. Запустите frontend (если не запущен):
```bash
cd frontend
bun run dev
```

Dev-сервер будет на http://localhost:3000 (Vite проксирует `/api` на backend:8001)

### 4. Откройте браузер:
```
http://localhost:3000
```

Вы увидите страницу входа NUMEX.

### 5. Войдите с тестовым аккаунтом:
- **Email:** `test@numex.app`
- **Пароль:** `Test123456`

После успешного входа откроется главная страница с режимами "План" и "Агент".

## Архитектура авторизации:

```
Frontend (localhost:3000)
    ↓ (логин форма)
Supabase Auth via Kong (localhost:8000/auth/v1)
    ↓ (создаёт JWT токен с user_id и email)
Frontend сохраняет токен в localStorage
    ↓ (все API запросы с Bearer token в заголовке)
Backend API (localhost:8001/api/v1)
    ↓ (проверяет JWT через SUPABASE_JWT_SECRET)
    ↓ (если пользователя нет в public.users - создаёт автоматически)
PostgreSQL Supabase (localhost:5432)
    ├── auth schema → Supabase Auth (auth.users, auth.sessions)
    └── public schema → Данные приложения (users, debts, optimization_plans)
```

**Важно:** Используется одна база данных Supabase PostgreSQL:
- **auth schema (порт 5432)**: управляется Supabase Auth
- **public schema (порт 5432)**: ваши таблицы приложения (`users`, `debts`, и т.д.)

Простая архитектура по принципу KISS - одна БД для всего!

## Почему раньше был HTTP Basic Auth:

`SITE_URL=http://localhost:3000` в Supabase `.env` определяет URL фронтенда. HTTP Basic Auth диалог появлялся потому, что:
1. Backend возвращал 401 Unauthorized (нет JWT токена)
2. Не было React-страницы логина
3. Браузер интерпретировал 401 как требование HTTP Basic Auth
4. Вводя логин/пароль от Supabase Dashboard (из supabase/.env), вы случайно проходили базовую аутентификацию на каком-то из сервисов

Теперь используется правильная авторизация через Supabase Auth с JWT токенами.

## Проверка работы:

После входа:
- **Режим "План"** должен показать 3 тестовых долга
- **Режим "Агент"** должен работать без запроса авторизации (UI компонент)
- При переключении между режимами авторизация сохраняется

## Отладка:

Если видите пустую страницу или ошибки:
1. Откройте DevTools (F12) → Console
2. Проверьте Network tab:
   - `POST http://localhost:8000/auth/v1/token` - должен вернуть токен при логине
   - `GET http://localhost:3000/api/v1/debts` - должен вернуть список долгов (проксируется на :8001)
3. Проверьте `.env` файлы:
   - `frontend/.env` - VITE_SUPABASE_URL и VITE_SUPABASE_ANON_KEY
   - `numex-app/.env` - SUPABASE_JWT_SECRET

## Переменные окружения:

### `frontend/.env`:
```
VITE_SUPABASE_URL=http://localhost:8000
VITE_SUPABASE_ANON_KEY=<из supabase/.env>
VITE_API_BASE=/api/v1
```

### `numex-app/.env`:
```
POSTGRES_PASSWORD=<из supabase/.env>
SUPABASE_JWT_SECRET=<из supabase/.env JWT_SECRET>
DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@localhost:5432/postgres
```

### `backend/.env` (для локального запуска):
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
SUPABASE_JWT_SECRET=<из supabase/.env JWT_SECRET>
REDIS_URL=redis://localhost:6379/0
```
