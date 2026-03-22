# RPML: Repayment Planning for Multiple Loans

Реализация MILP-модели Rios-Solis (2017) для оптимизации погашения нескольких кредитов: решатель OR-Tools (по умолчанию HiGHS, при необходимости SCIP), сравнение с жадными стратегиями (Avalanche, Snowball, Average).

## Установка

```bash
cd /path/to/RPML
uv sync
```

Для запуска тестов установите опциональную группу `dev`: `uv sync --extra dev`.

## Структура проекта

```
RPML/
├── src/rpml/           # пакет: данные, MILP, базовые стратегии, метрики, чекпоинт, экспорт траекторий
├── tests/              # модульные тесты
├── RiosSolisDataset/   # набор инстансов из статьи
├── run_experiments.py  # CLI для пакетных экспериментов
├── pyproject.toml
└── README.md
```

## Использование

### Данные

```python
from rpml.data_loader import load_instance, load_all_instances

instance = load_instance("path/to/file.dat")
instances = load_all_instances("RiosSolisDataset/Instances/Instances")
```

### MILP

```python
from rpml.milp_model import solve_rpml

solution = solve_rpml(instance, time_limit_seconds=300)
```

### Базовые стратегии

- **Avalanche** — сначала долги с большей ставкой.
- **Snowball** — сначала с меньшим остатком.
- **Average** — приоритет по средним ставкам.

```python
from rpml.baseline import debt_avalanche, debt_snowball, debt_average

avalanche_solution = debt_avalanche(instance)
snowball_solution = debt_snowball(instance)
```

### Эксперименты (`run_experiments.py`)

Скрипт читает инстансы из `RiosSolisDataset/Instances/Instances`, для каждого решает MILP и считает базовые стратегии Avalanche и Snowball, сохраняет агрегированные метрики. Датасет должен лежать рядом со скриптом в ожидаемой структуре каталогов.

**Базовый запуск** (последовательно, один процесс):

```bash
uv run python run_experiments.py
```

**Что по умолчанию**

| Параметр | Значение |
|----------|----------|
| Группы по числу кредитов | `-n 4 8` |
| Лимит времени MILP | `-t 300` с |
| Чекпоинт | `tmp/experiment_results_checkpoint.jsonl` |
| CSV с результатами | `tmp/experiment_results.csv` (пишется в конце и при `--summary`) |
| Журнал таймаутов | `tmp/timeout_instances.csv` |
| Решатель | сначала HiGHS; при отказе по таймауту в параллельном режиме — повтор с SCIP (если не отключено) |

**Основные опции**

- **`-m N` / `--max-instances N`** — не больше `N` инстансов в каждой группе (`-n`), удобно для быстрых прогонов.
- **`-n 4 8 12`** — какие размеры задач обрабатывать (только те, что есть в датасете).
- **`-t SEC` / `--time-limit SEC`** — лимит времени на один инстанс для MILP.
- **`--watchdog-grace-seconds SEC`** — дополнительное время к `-t` в параллельном режиме; по истечении «сторож» завершает зависший воркер (по умолчанию `15` с).
- **`-p` / `--parallel`** — несколько инстансов параллельно; **`-w N` / `--workers N`** — число процессов (по умолчанию — число ядер).
- **`--checkpoint PATH`** — файл чекпоинта (JSONL); при повторном запуске уже обработанные инстансы пропускаются.
- **`--restart`** — игнорировать существующий чекпоинт и начать с нуля.
- **`--summary`** — не считать заново: загрузить чекпоинт, вывести сводку метрик и обновить `tmp/experiment_results.csv`.
- **`--timeout-log PATH`** — куда писать/читать список инстансов, завершившихся по таймауту сторожа.
- **`--include-known-timeouts`** — не пропускать инстансы из журнала таймаутов (повторная попытка, например после смены лимита или решателя).
- **`--scip`** — сразу использовать SCIP для всех инстансов и отключить резервный переход HiGHS→SCIP.
- **`--export-timelines`** — для каждого обработанного инстанса сохранить JSON с помесячными платежами, остатками, накоплениями по MILP, Avalanche и Snowball (денежные поля в JSON — округление до 2 знаков).
- **`--timelines-dir PATH`** — каталог для этих JSON (по умолчанию `tmp/timelines`).

**Примеры**

```bash
# Быстрый прогон: только 4 кредита, по 3 инстанса в группе, лимит 60 с
uv run python run_experiments.py -n 4 -m 3 -t 60

# Параллельно, 8 потоков, с экспортом траекторий для графиков
uv run python run_experiments.py -p -w 8 --export-timelines

# Только SCIP, без fallback
uv run python run_experiments.py --scip -t 120

# Сводка по уже сохранённому чекпоинту без пересчёта
uv run python run_experiments.py --summary

# Полный пересчёт с новым чекпоинтом
uv run python run_experiments.py --restart --checkpoint tmp/run2.jsonl
```

Прерывание `Ctrl+C` в параллельном режиме завершает воркеры; при необходимости можно повторить запуск — обработанные инстансы подхватятся из чекпоинта.

## Тестирование

```bash
uv run --extra dev pytest tests/
```

При активированном `.venv`: `pytest tests/`.
