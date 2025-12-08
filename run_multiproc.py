"""
Многопроцессный запуск экспериментов RPML.

Гоняет solve_rpml + Debt Avalanche параллельно по инстансам.
"""

from functools import partial
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable, List, Tuple

from tqdm import tqdm

from rpml.baseline import debt_avalanche
from rpml.data_loader import get_instances_by_size, load_all_instances, load_instance
from rpml.metrics import ComparisonResult, compare_solutions, print_summary
from rpml.milp_model import solve_rpml


def _solve_single(dat_path: Path, n_loans: int, time_limit_seconds: int) -> ComparisonResult | None:
    """Решить один инстанс и вернуть ComparisonResult или None, если не удалось."""
    instance = load_instance(dat_path)
    optimal = solve_rpml(instance, time_limit_seconds=time_limit_seconds)

    if optimal.status not in ("OPTIMAL", "FEASIBLE"):
        return None

    baseline = debt_avalanche(instance)
    return compare_solutions(
        optimal=optimal,
        baseline=baseline,
        instance_name=instance.name,
        n_loans=n_loans,
    )


def run_experiments_multiproc(
    dataset_path: Path,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    allowed_n_loans: tuple[int, ...] = (4, 8, 12),
    n_jobs: int | None = None,
    verbose: bool = True,
) -> List[ComparisonResult]:
    """
    Запуск экспериментов в несколько процессов.

    Args:
        dataset_path: Путь к директории .dat
        max_instances_per_group: Лимит инстансов в каждой группе (None — все)
        time_limit_seconds: Лимит на решатель MILP
        allowed_n_loans: Какие размеры портфеля брать
        n_jobs: Число процессов (None => min(cpu_count, len(задач)))
        verbose: Печатать прогресс
    """
    if verbose:
        print("Загружаю инстансы...")
    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Всего инстансов: {len(instances)}")
        for n, group in grouped.items():
            print(f"  {n} займов: {len(group)}")

    tasks: List[Tuple[Path, int]] = []
    for n_loans in allowed_n_loans:
        group = grouped.get(n_loans, [])
        if not group:
            continue
        if max_instances_per_group:
            group = group[:max_instances_per_group]
        for inst in group:
            # Перечитываем по пути, чтобы уменьшить передачу данных между процессами
            tasks.append((dataset_path / f"{inst.name}.dat", n_loans))

    if not tasks:
        return []

    if n_jobs is None:
        n_jobs = max(1, min(cpu_count(), len(tasks)))

    if verbose:
        print(f"Стартую {len(tasks)} задач, процессов: {n_jobs}")

    results: List[ComparisonResult] = []
    worker = partial(_solve_single, time_limit_seconds=time_limit_seconds)

    # Импорт здесь, чтобы не тянуть вне функции
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        iterator: Iterable[ComparisonResult | None] = executor.map(worker, (p for p, _ in tasks), (n for _, n in tasks))
        if verbose:
            iterator = tqdm(iterator, total=len(tasks))
        for res in iterator:
            if res is not None:
                results.append(res)

    return results


def main():
    """CLI-обёртка."""
    dataset_path = Path(__file__).parent / "RiosSolisDataset" / "Instances" / "Instances"
    if not dataset_path.exists():
        print(f"Не найден путь к датасету: {dataset_path}")
        return

    results = run_experiments_multiproc(
        dataset_path=dataset_path,
        max_instances_per_group=None,
        time_limit_seconds=300,
        allowed_n_loans=(4, 8, 12),
        n_jobs=None,
        verbose=True,
    )

    print("\n" + "=" * 60)
    print_summary(results)

    if results:
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "instance": r.instance_name,
                    "n_loans": r.n_loans,
                    "optimal_cost": r.optimal_cost,
                    "baseline_cost": r.baseline_cost,
                    "savings_pct": r.relative_savings,
                    "solve_time": r.optimal_solve_time,
                    "gap": r.optimal_gap,
                    "status": r.optimal_status,
                }
                for r in results
            ]
        )
        output_path = Path(__file__).parent / "experiment_results_multiproc.csv"
        df.to_csv(output_path, index=False)
        print(f"\nСохранил результаты: {output_path}")


if __name__ == "__main__":
    main()
