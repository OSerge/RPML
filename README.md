# RPML: Repayment Planning for Multiple Loans

Реализация MILP-модели Rios-Solis (2017) для оптимизации погашения множественных кредитов.

## Установка зависимостей

Используя uv (рекомендуется):
```bash
cd /path/to/RPML
uv sync
```

Это создаст виртуальное окружение `.venv` и установит все зависимости из `pyproject.toml`.

## Структура проекта

```
RPML/
├── src/
│   └── rpml/
│       ├── __init__.py
│       ├── data_loader.py      # Парсинг .dat файлов
│       ├── milp_model.py        # MILP модель (OR-Tools + HiGHS)
│       ├── baseline.py          # Baseline алгоритмы
│       └── metrics.py           # Метрики сравнения
├── tests/
│   ├── __init__.py
│   ├── test_data_loader.py
│   └── test_baseline.py
├── RiosSolisDataset/        # Датасет из статьи
├── run_experiments.py       # Скрипт для запуска экспериментов
├── pyproject.toml           # Конфигурация проекта и зависимости
└── README.md
```

## Использование

### Загрузка данных
```python
from rpml.data_loader import load_instance, load_all_instances

# Загрузить один instance
instance = load_instance("path/to/file.dat")

# Загрузить все instances
instances = load_all_instances("RiosSolisDataset/Instances/Instances")
```

### Решение MILP модели
```python
from rpml.milp_model import solve_rpml

solution = solve_rpml(instance, time_limit_seconds=300)
print(f"Objective value: {solution.objective_value}")
print(f"Status: {solution.status}")
print(f"Solve time: {solution.solve_time:.2f}s")
print(f"Gap: {solution.gap:.2f}%")
```

### Baseline алгоритмы
```python
from rpml.baseline import debt_avalanche, debt_snowball, debt_average

avalanche_solution = debt_avalanche(instance)
snowball_solution = debt_snowball(instance)
average_solution = debt_average(instance)
```

### Запуск экспериментов
```bash
cd /path/to/RPML
uv run python run_experiments.py
```

## Тестирование

```bash
cd /path/to/RPML
uv run pytest tests/
```

Или если виртуальное окружение уже активировано:
```bash
pytest tests/
```

## Ожидаемые результаты

На датасете Rios-Solis (550 instances):
- 4 кредита: ~5.84% экономия vs Debt Avalanche
- 8 кредитов: ~4.62% экономия
- 12 кредитов: ~3.43% экономия
