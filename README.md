# Репозиторий NUMEX и RPML

Этот репозиторий содержит:

- **NUMEX** (`numex-app/`) — приложение для персональных финансов с оптимизацией погашения долгов
- **RPML** (`rpml/`) — библиотека для оптимизации погашения множественных кредитов (MILP-модель Rios-Solis 2017)

## Структура проекта

```
RPML/
├── numex-app/           # FinTech приложение (FastAPI backend, React frontend, Supabase)
│   ├── backend/         # FastAPI, использует rpml для оптимизации
│   ├── frontend/        # React UI
│   ├── supabase/        # Self-hosted Supabase (PostgreSQL, Auth, Kong)
│   └── README.md        # Инструкции по запуску приложения
│
└── rpml/                # Библиотека RPML (отдельный пакет)
    ├── src/rpml/        # Исходный код библиотеки
    ├── tests/           # Тесты
    ├── run_experiments.py
    ├── RiosSolisDataset/
    ├── pyproject.toml
    └── README.md        # Документация библиотеки RPML
```

## Быстрый старт

### NUMEX приложение

См. подробные инструкции в [numex-app/README.md](numex-app/README.md) и [numex-app/SETUP.md](numex-app/SETUP.md).

```bash
cd numex-app
# Настроить и запустить Supabase, backend, frontend
```

### RPML библиотека

Библиотека для разработки и исследований алгоритмов оптимизации погашения долгов.

```bash
cd rpml

# Установка (pip или uv)
pip install -e .
# или
uv sync

# Запуск тестов
pytest tests/

# Запуск экспериментов
python run_experiments.py
```

Полная документация RPML: см. [rpml/README.md](rpml/README.md)

## Архитектура

- **NUMEX backend** использует `rpml` как path-зависимость: пакет устанавливается из локальной директории `rpml/` в editable-режиме
- **RPML** — независимый пакет, можно разрабатывать и тестировать отдельно, при необходимости выделить в отдельный репозиторий
