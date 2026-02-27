# NUMEX Frontend

Современный финансовый интерфейс для управления долгами с AI-агентом.

## Технологии

- **React 18** с TypeScript
- **Vite** - быстрая сборка и dev-сервер
- **TanStack Query** - управление состоянием и кэширование API запросов
- **Motion** (Framer Motion) - плавные анимации
- **Tailwind CSS** - утилитарные стили
- **Lucide React** - иконки

## Требования

- **Bun** >= 1.0 (рекомендуется) или Node.js >= 18.0.0

## Установка и запуск через Bun

Установка зависимостей:

```bash
bun install
```

Запуск dev-сервера:

```bash
bun run dev
```

Приложение будет доступно по адресу **http://localhost:3000** (прокси `/api` идёт на `http://localhost:8000` — бэкенд должен быть запущен отдельно).

Сборка для production:

```bash
bun run build
```

Готовые файлы будут в директории `dist/`.

## Альтернатива: npm

```bash
npm install
npm run dev
```

## Проверка запуска

**Только фронтенд (Docker):** из корня `numex-app`:
```bash
docker compose build frontend
docker run -d -p 3000:80 --name numex-frontend numex-app-frontend
```
Открой http://localhost:3000 — должна открыться страница NUMEX (План/Агент). Запросы к API без бэкенда будут падать по таймауту или 502.

**Полный стек (фронт + бэкенд + БД):** из корня `numex-app`:
```bash
export SUPABASE_JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long
docker compose up -d postgres redis supabase-auth backend frontend
```
Первый запуск долгий (сборка бэкенда, образ GoTrue). Фронт: http://localhost:3000, health бэкенда: `curl http://localhost:3000/api/v1/` (через прокси) или из контейнера backend порт 8000.

**Локально (Bun или Node 18+):** в каталоге `frontend`:
```bash
bun install && bun run dev
# или: npm install && npm run dev
```
Бэкенд должен быть запущен на порту 8000 (Vite проксирует `/api` на него).

## Структура проекта

```
src/
├── App.tsx                    # Основное приложение с переключателем План/Агент
├── main.tsx                   # Точка входа
├── index.css                  # Глобальные стили и CSS переменные
├── components/
│   ├── Plan.tsx               # План погашения долгов
│   ├── Agent.tsx              # AI-агент для консультаций
│   ├── DebtCards.tsx          # Карточки долгов
│   ├── PaymentCalendar.tsx    # Календарь платежей
│   ├── OptimizationPanel.tsx  # Панель оптимизации
│   └── DebtTimeline.tsx       # Timeline погашения долгов
├── hooks/
│   └── useDebts.ts            # Хуки для работы с долгами
├── services/
│   └── api.ts                 # API клиент
├── types/
│   └── debt.ts                # TypeScript типы
└── lib/
    ├── utils.ts               # Утилиты для стилей
    └── supabase.ts            # Supabase клиент
```

## Основные возможности

### Режим "План"
- Статистика по долгам (общая сумма, ежемесячный платеж, средняя ставка)
- Карточки долгов с прогрессом погашения
- Календарь платежей
- Панель AI-оптимизации с рекомендациями
- Timeline погашения долгов

### Режим "Агент"
- AI-чат для финансовых консультаций
- Insights с предупреждениями и рекомендациями
- Быстрые вопросы для начала диалога
- Подключение к `/api/v1/explain` endpoint

## API Integration

Фронтенд подключается к backend API на `/api/v1`:

- `GET /api/v1/debts` - получение списка долгов
- `POST /api/v1/debts` - создание нового долга
- `POST /api/v1/optimize` - запуск оптимизации
- `POST /api/v1/explain` - AI объяснения
- `GET /api/v1/budget/summary` - сводка по бюджету

## Темная тема

Приложение поддерживает светлую и темную темы через класс `.dark` на корневом элементе.

## Дизайн

Дизайн основан на современном Figma прототипе с:
- Градиентами (indigo, purple)
- Закругленными углами (rounded-2xl)
- Плавными анимациями при переключении режимов
- Адаптивной версткой для мобильных и десктопов

## Авторизация через Supabase

### Настройка

1. Запустите Supabase из директории `../supabase`:
```bash
cd ../supabase
docker compose up -d
```

2. Создайте тестового пользователя. Можно использовать утилиту `db-passwd.sh`:
```bash
cd ../supabase
./utils/db-passwd.sh create user@example.com password123
```

Или создайте пользователя через Supabase Studio:
- Откройте http://localhost:8000
- Войдите с логином/паролем из `supabase/.env` (DASHBOARD_USERNAME/DASHBOARD_PASSWORD)
- Перейдите в Authentication > Users > Add User

3. Настройте переменные окружения в `frontend/.env`:
```env
VITE_SUPABASE_URL=http://localhost:8000
VITE_SUPABASE_ANON_KEY=<ANON_KEY из supabase/.env>
```

### Вход в приложение

Запустите frontend:
```bash
bun run dev
```

Откройте http://localhost:5173 и войдите с email/паролем созданного пользователя.
