"""
Run experiments on Rios-Solis dataset.

Compares optimal MILP solutions with baseline strategies.
"""

import argparse
import csv
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import numpy as np
from tqdm import tqdm

from rpml.data_loader import load_all_instances, get_instances_by_size
from rpml.milp_model import DEFAULT_SOLVER, FALLBACK_SOLVER, solve_rpml
from rpml.baseline import debt_avalanche, debt_snowball
from rpml.metrics import (
    ComparisonResult,
    compare_solutions,
    print_summary,
    validate_baseline_solution,
)
from rpml.checkpoint import CheckpointManager
from rpml.timeline_export import export_timeline_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


TIMEOUT_CSV_COLUMNS = [
    "instance_name",
    "n_loans",
    "time_limit_seconds",
    "watchdog_timeout_seconds",
    "reason",
    "recorded_at_utc",
]


def resolve_solver_strategy(use_scip: bool) -> tuple[str, bool]:
    """Return initial solver and whether HiGHS->SCIP fallback is enabled."""
    if use_scip:
        return FALLBACK_SOLVER, False
    return DEFAULT_SOLVER, True


def load_timeout_instances(timeout_log_path: Path | None) -> set[str]:
    """Load timed-out instance names from timeout CSV log."""
    if timeout_log_path is None or not timeout_log_path.exists():
        return set()
    out: set[str] = set()
    try:
        with open(timeout_log_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("instance_name") or "").strip()
                if name:
                    out.add(name)
    except Exception:
        # Best-effort log loading; experiment should still run.
        return set()
    return out


def append_timeout_records(timeout_log_path: Path | None, records: list[dict]) -> None:
    """Append unique timeout records to CSV log."""
    if timeout_log_path is None or not records:
        return
    timeout_log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_timeout_instances(timeout_log_path)
    is_new_file = not timeout_log_path.exists()
    with open(timeout_log_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TIMEOUT_CSV_COLUMNS)
        if is_new_file:
            writer.writeheader()
        for rec in records:
            name = rec.get("instance_name")
            if not name or name in existing:
                continue
            writer.writerow(rec)
            existing.add(name)


def remove_timeout_instances(timeout_log_path: Path | None, instance_names: set[str]) -> None:
    """Remove successfully solved instances from timeout CSV log."""
    if timeout_log_path is None or not timeout_log_path.exists() or not instance_names:
        return
    try:
        with open(timeout_log_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = [row for row in reader if (row.get("instance_name") or "").strip() not in instance_names]
        with open(timeout_log_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TIMEOUT_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        # Best-effort cleanup only.
        return


def run_experiments(
    dataset_path: Path,
    max_instances_per_group: int = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    checkpoint_path: Path | None = None,
    timeout_log_path: Path | None = None,
    skip_known_timeouts: bool = True,
    restart: bool = False,
    solver_name: str = DEFAULT_SOLVER,
    export_timelines: bool = False,
    timelines_dir: Path | None = None,
) -> List[ComparisonResult]:
    """
    Run experiments on all instances.

    Results are saved incrementally to the checkpoint file. Already processed
    instances are skipped on resume.
    """
    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        for n, group in grouped.items():
            print(f"  {n} loans: {len(group)} instances")

    checkpoint = (
        CheckpointManager(checkpoint_path, restart=restart)
        if checkpoint_path
        else None
    )
    processed = checkpoint.get_processed_instances() if checkpoint else set()
    
    if verbose and checkpoint_path:
        if processed:
            print(f"Resuming: {len(processed)} instances already in checkpoint")
        else:
            print("Starting fresh (no checkpoint found or checkpoint is empty)")

    known_timeouts = load_timeout_instances(timeout_log_path) if skip_known_timeouts else set()
    if verbose and timeout_log_path:
        if known_timeouts:
            print(f"Skipping {len(known_timeouts)} known timeout instance(s) from: {timeout_log_path}")
        else:
            print(f"No known timeout instances in: {timeout_log_path}")

    results = []

    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])

        if not group_instances:
            continue

        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]

        if verbose:
            print(f"\nProcessing {n_loans}-loan instances ({len(group_instances)} instances)...")

        iterator = tqdm(group_instances, file=sys.stdout) if verbose else group_instances

        for instance in iterator:
            if instance.name in processed:
                if verbose:
                    tqdm.write(f"Skipping {instance.name} (already processed)", file=sys.stdout)
                continue
            if instance.name in known_timeouts:
                if verbose:
                    tqdm.write(f"Skipping {instance.name} (known timeout)", file=sys.stdout)
                continue

            try:
                optimal_solution = solve_rpml(
                    instance,
                    time_limit_seconds=time_limit_seconds,
                    solver_name=solver_name,
                )

                avalanche_solution = debt_avalanche(instance)
                snowball_solution = debt_snowball(instance)
                avalanche_valid, avalanche_errors, avalanche_final_balance = validate_baseline_solution(
                    avalanche_solution, instance
                )
                snowball_valid, snowball_errors, snowball_final_balance = validate_baseline_solution(
                    snowball_solution, instance
                )
                avalanche_feasible = avalanche_valid and avalanche_final_balance < 1.0
                snowball_feasible = snowball_valid and snowball_final_balance < 1.0

                if optimal_solution.status not in ["OPTIMAL", "FEASIBLE"]:
                    if verbose:
                        tqdm.write(f"Warning: {instance.name} MILP status: {optimal_solution.status}", file=sys.stdout)
                if verbose and not avalanche_valid:
                    tqdm.write(
                        f"  {instance.name}: Debt Avalanche invalid ({'; '.join(avalanche_errors[:2])})",
                        file=sys.stdout,
                    )
                if verbose and not avalanche_feasible:
                    tqdm.write(
                        f"  {instance.name}: Debt Avalanche not repaid by T (max balance: {avalanche_final_balance:,.0f})",
                        file=sys.stdout,
                    )
                if verbose and not snowball_valid:
                    tqdm.write(
                        f"  {instance.name}: Debt Snowball invalid ({'; '.join(snowball_errors[:2])})",
                        file=sys.stdout,
                    )
                if verbose and not snowball_feasible:
                    tqdm.write(
                        f"  {instance.name}: Debt Snowball not repaid by T (max balance: {snowball_final_balance:,.0f})",
                        file=sys.stdout,
                    )

                comparison = compare_solutions(
                    optimal=optimal_solution,
                    avalanche=avalanche_solution,
                    snowball=snowball_solution,
                    instance_name=instance.name,
                    n_loans=n_loans,
                    avalanche_valid=avalanche_valid,
                    avalanche_repaid_by_T=avalanche_feasible,
                    avalanche_final_balance=avalanche_final_balance,
                    snowball_valid=snowball_valid,
                    snowball_repaid_by_T=snowball_feasible,
                    snowball_final_balance=snowball_final_balance,
                )

                if export_timelines and timelines_dir is not None:
                    export_timeline_json(
                        output_dir=timelines_dir,
                        instance=instance,
                        comparison=comparison,
                        optimal_solution=optimal_solution,
                        avalanche_solution=avalanche_solution,
                        snowball_solution=snowball_solution,
                    )

                results.append(comparison)
                if checkpoint:
                    checkpoint.save_result(comparison)
                remove_timeout_instances(timeout_log_path, {instance.name})
                processed.add(instance.name)

            except Exception as e:
                if verbose:
                    print(f"\nError processing {instance.name}: {e}")
                continue

    if checkpoint:
        results = list(checkpoint.load_existing_results().values())
    return results


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run RPML experiments on Rios-Solis dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "-m", "--max-instances",
        type=int,
        default=None,
        metavar="N",
        help="Maximum instances per loan group (None = all)",
    )
    
    parser.add_argument(
        "-n", "--n-loans",
        type=int,
        nargs="+",
        default=[4, 8],
        metavar="N",
        help="Loan counts to process (e.g., -n 4 8 12)",
    )
    
    parser.add_argument(
        "-t", "--time-limit",
        type=int,
        default=300,
        metavar="SEC",
        help="Time limit for MILP solver in seconds",
    )
    parser.add_argument(
        "--watchdog-grace-seconds",
        type=int,
        default=15,
        metavar="SEC",
        help="Extra seconds above --time-limit before watchdog kills a stuck worker",
    )
    
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Enable multiprocessing for parallel instance solving",
    )
    
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel workers (default: CPU count)",
    )
    
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to checkpoint file (default: tmp/experiment_results_checkpoint.jsonl)",
    )
    
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Ignore existing checkpoint and start fresh",
    )
    
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary of existing checkpoint results and exit (don't run experiments)",
    )
    parser.add_argument(
        "--timeout-log",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to timeout CSV log (default: tmp/timeout_instances.csv)",
    )
    parser.add_argument(
        "--include-known-timeouts",
        action="store_true",
        help="Process instances listed in timeout log instead of skipping them",
    )
    parser.add_argument(
        "--scip",
        action="store_true",
        help="Use SCIP directly for all instances and disable HiGHS->SCIP fallback",
    )
    parser.add_argument(
        "--export-timelines",
        action="store_true",
        help="Export per-instance monthly trajectories to JSON files",
    )
    parser.add_argument(
        "--timelines-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Directory for timeline JSON files (default: tmp/timelines)",
    )
    
    return parser.parse_args()


def process_instance(args_tuple):
    """Process a single instance (for multiprocessing)."""
    (
        instance,
        time_limit_seconds,
        verbose,
        checkpoint_path,
        processed_set,
        solver_name,
        export_timelines,
        timelines_dir_str,
    ) = args_tuple

    if processed_set is not None and instance.name in processed_set:
        return ("skip_processed", instance.name)

    try:
        optimal_solution = solve_rpml(
            instance,
            time_limit_seconds=time_limit_seconds,
            solver_name=solver_name,
        )

        avalanche_solution = debt_avalanche(instance)
        snowball_solution = debt_snowball(instance)
        avalanche_valid, _, avalanche_final_balance = validate_baseline_solution(
            avalanche_solution, instance
        )
        snowball_valid, _, snowball_final_balance = validate_baseline_solution(
            snowball_solution, instance
        )
        avalanche_feasible = avalanche_valid and avalanche_final_balance < 1.0
        snowball_feasible = snowball_valid and snowball_final_balance < 1.0

        comparison = compare_solutions(
            optimal=optimal_solution,
            avalanche=avalanche_solution,
            snowball=snowball_solution,
            instance_name=instance.name,
            n_loans=instance.n,
            avalanche_valid=avalanche_valid,
            avalanche_repaid_by_T=avalanche_feasible,
            avalanche_final_balance=avalanche_final_balance,
            snowball_valid=snowball_valid,
            snowball_repaid_by_T=snowball_feasible,
            snowball_final_balance=snowball_final_balance,
        )

        if export_timelines and timelines_dir_str is not None:
            export_timeline_json(
                output_dir=Path(timelines_dir_str),
                instance=instance,
                comparison=comparison,
                optimal_solution=optimal_solution,
                avalanche_solution=avalanche_solution,
                snowball_solution=snowball_solution,
            )

        if checkpoint_path is not None:
            checkpoint = CheckpointManager(Path(str(checkpoint_path)))
            checkpoint.save_result(comparison)
        status = optimal_solution.status
        result_kind = "ok" if status in ("OPTIMAL", "FEASIBLE") else "ok_infeasible"
        return (result_kind, comparison, solver_name)

    except Exception as e:
        return ("error", instance.name, str(e), solver_name)


def run_experiments_parallel(
    dataset_path: Path,
    max_instances_per_group: int = None,
    time_limit_seconds: int = 300,
    watchdog_grace_seconds: int = 15,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    n_workers: int = None,
    checkpoint_path: Path | None = None,
    timeout_log_path: Path | None = None,
    skip_known_timeouts: bool = True,
    restart: bool = False,
    initial_solver_name: str = DEFAULT_SOLVER,
    enable_solver_fallback: bool = True,
    export_timelines: bool = False,
    timelines_dir: Path | None = None,
) -> List[ComparisonResult]:
    """
    Run experiments on all instances using multiprocessing.

    Results are saved incrementally to the checkpoint file. Already processed
    instances are skipped on resume.
    """
    from multiprocessing import cpu_count

    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        for n, group in grouped.items():
            print(f"  {n} loans: {len(group)} instances")

    all_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])

        if not group_instances:
            continue

        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]

        all_instances.extend(group_instances)

    checkpoint = (
        CheckpointManager(checkpoint_path, restart=restart)
        if checkpoint_path
        else None
    )
    processed = checkpoint.get_processed_instances() if checkpoint else set()
    
    if verbose and checkpoint_path:
        if processed:
            print(f"Resuming: {len(processed)} instances already in checkpoint")
        else:
            print("Starting fresh (no checkpoint found or checkpoint is empty)")

    known_timeouts = load_timeout_instances(timeout_log_path) if skip_known_timeouts else set()
    to_process = [
        inst
        for inst in all_instances
        if inst.name not in processed and inst.name not in known_timeouts
    ]
    if verbose:
        print(f"\nProcessing {len(to_process)} instances in parallel...")
        if processed:
            print(f"  (Skipped {len(all_instances) - len(to_process)} already processed)")
        if known_timeouts:
            print(f"  (Skipped {len(known_timeouts)} known timeout instance(s))")

    ck_path_str = str(checkpoint_path) if checkpoint_path else None
    timelines_dir_str = str(timelines_dir) if timelines_dir else None
    args_list = [
        (
            inst,
            time_limit_seconds,
            False,
            ck_path_str,
            processed,
            initial_solver_name,
            export_timelines,
            timelines_dir_str,
        )
        for inst in to_process
    ]

    n_workers = n_workers or cpu_count()
    if verbose:
        print(f"Using {n_workers} workers")

    # External hard timeout per worker task. Keep it close to the MILP limit so
    # a hung solver does not stall the pool much longer than requested.
    per_instance_timeout = time_limit_seconds + watchdog_grace_seconds

    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    import time
    from collections import deque

    def _kill_executor_workers(executor: ProcessPoolExecutor) -> None:
        # Hard-stop worker processes when a solver run hangs (ignores internal limits).
        processes = getattr(executor, "_processes", {}) or {}
        for proc in processes.values():
            try:
                proc.kill()
            except Exception:
                pass
        executor.shutdown(wait=False, cancel_futures=True)

    raw_results = []
    pending_args = deque(args_list)
    completed_instances = set(processed)
    pbar_ctx = tqdm(total=len(args_list), file=sys.stdout) if verbose else nullcontext()

    try:
        with pbar_ctx as pbar:
            while pending_args:
                executor = ProcessPoolExecutor(max_workers=n_workers)
                inflight: dict = {}
                try:
                    while pending_args and len(inflight) < n_workers:
                        args = pending_args.popleft()
                        future = executor.submit(process_instance, args)
                        inflight[future] = (args, time.time())

                    while inflight:
                        done, _ = wait(inflight.keys(), timeout=1.0, return_when=FIRST_COMPLETED)

                        # Consume completed futures first
                        for future in done:
                            (args, _) = inflight.pop(future)
                            inst = args[0]
                            try:
                                result = future.result()
                                raw_results.append(result)
                                if result and result[0] in ("ok", "ok_infeasible"):
                                    remove_timeout_instances(timeout_log_path, {inst.name})
                                    completed_instances.add(inst.name)
                            except Exception as e:
                                raw_results.append(("error", inst.name, str(e)))
                            finally:
                                if pbar is not None:
                                    pbar.update(1)

                        # Backfill workers
                        while pending_args and len(inflight) < n_workers:
                            args = pending_args.popleft()
                            future = executor.submit(process_instance, args)
                            inflight[future] = (args, time.time())

                        # Watchdog: if any task runs too long, kill the whole pool and continue.
                        now = time.time()
                        timed_out = [
                            (future, args)
                            for future, (args, started_at) in inflight.items()
                            if (now - started_at) > per_instance_timeout
                        ]
                        if timed_out:
                            timeout_names = [args[0].name for _, args in timed_out]
                            timeout_records = []
                            for _, args in timed_out:
                                inst = args[0]
                                solver_name = args[5]
                                if enable_solver_fallback and solver_name == DEFAULT_SOLVER:
                                    retry_args = (
                                        inst,
                                        time_limit_seconds,
                                        False,
                                        ck_path_str,
                                        processed,
                                        FALLBACK_SOLVER,
                                        export_timelines,
                                        timelines_dir_str,
                                    )
                                    pending_args.appendleft(retry_args)
                                    if verbose:
                                        print(f"\nRetrying {inst.name} with {FALLBACK_SOLVER} after {DEFAULT_SOLVER} timeout")
                                else:
                                    raw_results.append(
                                        ("error", inst.name, f"Watchdog timeout > {per_instance_timeout:.0f}s after {solver_name}")
                                    )
                                    completed_instances.add(inst.name)
                                    timeout_records.append(
                                        {
                                            "instance_name": inst.name,
                                            "n_loans": inst.n,
                                            "time_limit_seconds": time_limit_seconds,
                                            "watchdog_timeout_seconds": int(per_instance_timeout),
                                            "reason": f"watchdog_timeout_after_{solver_name.lower()}",
                                            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                                        }
                                    )
                                    if pbar is not None:
                                        pbar.update(1)
                            append_timeout_records(timeout_log_path, timeout_records)

                            # Requeue non-timeout in-flight tasks (they were killed with the pool).
                            for future, (args, _) in inflight.items():
                                if args[0].name not in timeout_names:
                                    pending_args.appendleft(args)
                            inflight.clear()

                            if verbose:
                                print(
                                    f"\nWatchdog: killed worker pool due to timeout on {len(timeout_names)} instance(s): "
                                    + ", ".join(timeout_names[:3])
                                    + ("..." if len(timeout_names) > 3 else "")
                                )
                            _kill_executor_workers(executor)
                            break
                except KeyboardInterrupt:
                    print("\nInterrupted by user. Shutting down workers...")
                    _kill_executor_workers(executor)
                    raise
                finally:
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass

                # Filter out already completed args after a watchdog restart.
                if pending_args:
                    pending_args = deque([a for a in pending_args if a[0].name not in completed_instances])
    except KeyboardInterrupt:
        import os
        # Fallback cleanup for stubborn children.
        os.system("pkill -f 'run-experiments' || true")
        print("Workers terminated.")
        sys.exit(1)

    for r in raw_results:
        if r is None:
            continue
        if r[0] == "skip_processed":
            pass
        elif r[0] == "skip_status" and verbose:
            print(f"  Skipped {r[1]}: status {r[2]}")
        elif r[0] == "error" and verbose:
            print(f"  Error {r[1]}: {r[2]}")

    if checkpoint:
        return list(checkpoint.load_existing_results().values())
    results = []
    for r in raw_results:
        if r is not None and r[0] in ("ok", "ok_infeasible"):
            results.append(r[1])
    return results


def main():
    """Main entry point."""
    args = parse_args()

    dataset_path = PROJECT_ROOT / "RiosSolisDataset" / "Instances" / "Instances"

    if not dataset_path.exists():
        print(f"Error: Dataset path not found: {dataset_path}")
        return

    tmp_dir = PROJECT_ROOT / "tmp"
    checkpoint_path = args.checkpoint or (tmp_dir / "experiment_results_checkpoint.jsonl")
    timeout_log_path = args.timeout_log or (tmp_dir / "timeout_instances.csv")
    timelines_dir = args.timelines_dir or (tmp_dir / "timelines")
    initial_solver_name, enable_solver_fallback = resolve_solver_strategy(args.scip)

    # Handle --summary mode
    if args.summary:
        print("=" * 60)
        print("RPML EXPERIMENT RESULTS SUMMARY")
        print("=" * 60)
        print(f"\nLoading results from: {checkpoint_path}\n")
        
        checkpoint = CheckpointManager(checkpoint_path)
        results = list(checkpoint.load_existing_results().values())
        
        if not results:
            print("No results found in checkpoint.")
            return
        
        print_summary(results)
        
        csv_path = tmp_dir / "experiment_results.csv"
        checkpoint.export_to_csv(csv_path)
        if results:
            print(f"\nResults exported to: {csv_path}")
        return

    print("=" * 60)
    print("RPML EXPERIMENTS")
    print("=" * 60)
    print("\nRunning experiments on Rios-Solis dataset...")
    print("Comparing optimal MILP with Debt Avalanche and Debt Snowball baselines.")
    print(f"\nParameters:")
    print(f"  Max instances per group: {args.max_instances or 'all'}")
    print(f"  Loan counts: {args.n_loans}")
    print(f"  Time limit: {args.time_limit}s")
    print(f"  Watchdog timeout: {args.time_limit + args.watchdog_grace_seconds}s")
    print(f"  Initial solver: {initial_solver_name}")
    print(f"  HiGHS->SCIP fallback: {'enabled' if enable_solver_fallback else 'disabled'}")
    print(f"  Multiprocessing: {'enabled' if args.parallel else 'disabled'}")
    if args.parallel:
        print(f"  Workers: {args.workers or 'auto (CPU count)'}")
    print(f"  Checkpoint: {checkpoint_path}")
    print(f"  Timeout log: {timeout_log_path}")
    print(f"  Export timelines: {'yes' if args.export_timelines else 'no'}")
    if args.export_timelines:
        print(f"  Timelines dir: {timelines_dir}")
    print(f"  Skip known timeouts: {'no' if args.include_known_timeouts else 'yes'}")
    if args.restart:
        print("  Restart: yes (ignoring existing checkpoint)")
    print()

    if args.parallel:
        results = run_experiments_parallel(
            dataset_path=dataset_path,
            max_instances_per_group=args.max_instances,
            time_limit_seconds=args.time_limit,
            watchdog_grace_seconds=args.watchdog_grace_seconds,
            verbose=True,
            allowed_n_loans=tuple(args.n_loans),
            n_workers=args.workers,
            checkpoint_path=checkpoint_path,
            timeout_log_path=timeout_log_path,
            skip_known_timeouts=not args.include_known_timeouts,
            restart=args.restart,
            initial_solver_name=initial_solver_name,
            enable_solver_fallback=enable_solver_fallback,
            export_timelines=args.export_timelines,
            timelines_dir=timelines_dir,
        )
    else:
        results = run_experiments(
            dataset_path=dataset_path,
            max_instances_per_group=args.max_instances,
            time_limit_seconds=args.time_limit,
            verbose=True,
            allowed_n_loans=tuple(args.n_loans),
            checkpoint_path=checkpoint_path,
            timeout_log_path=timeout_log_path,
            skip_known_timeouts=not args.include_known_timeouts,
            restart=args.restart,
            solver_name=initial_solver_name,
            export_timelines=args.export_timelines,
            timelines_dir=timelines_dir,
        )

    print("\n" + "=" * 60)
    print_summary(results)

    checkpoint = CheckpointManager(checkpoint_path)
    csv_path = tmp_dir / "experiment_results.csv"
    checkpoint.export_to_csv(csv_path)
    if checkpoint.load_existing_results():
        print(f"\nResults exported to: {csv_path}")
    if timeout_log_path.exists():
        print(f"Timeout instances logged to: {timeout_log_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
        import os
        os.system("pkill -f 'run-experiments' || true")
        import sys
        sys.exit(1)
