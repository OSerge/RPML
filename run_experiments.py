"""
Run experiments on Rios-Solis dataset.

Compares optimal MILP solutions with baseline strategies.
"""

import argparse
import sys
from pathlib import Path
from typing import List

import numpy as np
from tqdm import tqdm

from rpml.data_loader import load_all_instances, get_instances_by_size
from rpml.milp_model import solve_rpml
from rpml.baseline import debt_avalanche, debt_snowball
from rpml.metrics import compare_solutions, print_summary, ComparisonResult
from rpml.checkpoint import CheckpointManager


def run_experiments(
    dataset_path: Path,
    max_instances_per_group: int = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    checkpoint_path: Path | None = None,
    restart: bool = False,
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

            try:
                optimal_solution = solve_rpml(instance, time_limit_seconds=time_limit_seconds)

                avalanche_solution = debt_avalanche(instance)
                snowball_solution = debt_snowball(instance)
                avalanche_feasible = bool(np.max(np.abs(avalanche_solution.balances[:, -1])) < 1.0)
                snowball_feasible = bool(np.max(np.abs(snowball_solution.balances[:, -1])) < 1.0)

                if optimal_solution.status not in ["OPTIMAL", "FEASIBLE"]:
                    if verbose:
                        tqdm.write(f"Warning: {instance.name} MILP status: {optimal_solution.status}", file=sys.stdout)
                if verbose and not avalanche_feasible:
                    tqdm.write(f"  {instance.name}: Debt Avalanche infeasible (max balance: {np.max(np.abs(avalanche_solution.balances[:, -1])):,.0f})", file=sys.stdout)
                if verbose and not snowball_feasible:
                    tqdm.write(f"  {instance.name}: Debt Snowball infeasible (max balance: {np.max(np.abs(snowball_solution.balances[:, -1])):,.0f})", file=sys.stdout)

                comparison = compare_solutions(
                    optimal=optimal_solution,
                    avalanche=avalanche_solution,
                    snowball=snowball_solution,
                    instance_name=instance.name,
                    n_loans=n_loans,
                    avalanche_feasible=avalanche_feasible,
                    snowball_feasible=snowball_feasible,
                )

                results.append(comparison)
                if checkpoint:
                    checkpoint.save_result(comparison)
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
    
    return parser.parse_args()


def process_instance(args_tuple):
    """Process a single instance (for multiprocessing)."""
    instance, time_limit_seconds, verbose, checkpoint_path, processed_set = args_tuple

    if processed_set is not None and instance.name in processed_set:
        return ("skip_processed", instance.name)

    try:
        optimal_solution = solve_rpml(instance, time_limit_seconds=time_limit_seconds)

        avalanche_solution = debt_avalanche(instance)
        snowball_solution = debt_snowball(instance)
        avalanche_feasible = bool(np.max(np.abs(avalanche_solution.balances[:, -1])) < 1.0)
        snowball_feasible = bool(np.max(np.abs(snowball_solution.balances[:, -1])) < 1.0)

        comparison = compare_solutions(
            optimal=optimal_solution,
            avalanche=avalanche_solution,
            snowball=snowball_solution,
            instance_name=instance.name,
            n_loans=instance.n,
            avalanche_feasible=avalanche_feasible,
            snowball_feasible=snowball_feasible,
        )

        if checkpoint_path is not None:
            checkpoint = CheckpointManager(Path(str(checkpoint_path)))
            checkpoint.save_result(comparison)
        status = optimal_solution.status
        return ("ok", comparison) if status in ("OPTIMAL", "FEASIBLE") else ("ok_infeasible", comparison)

    except Exception as e:
        return ("error", instance.name, str(e))


def run_experiments_parallel(
    dataset_path: Path,
    max_instances_per_group: int = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    n_workers: int = None,
    checkpoint_path: Path | None = None,
    restart: bool = False,
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

    to_process = [inst for inst in all_instances if inst.name not in processed]
    if verbose:
        print(f"\nProcessing {len(to_process)} instances in parallel...")
        if processed:
            print(f"  (Skipped {len(all_instances) - len(to_process)} already processed)")

    ck_path_str = str(checkpoint_path) if checkpoint_path else None
    args_list = [(inst, time_limit_seconds, False, ck_path_str, processed) for inst in to_process]

    n_workers = n_workers or cpu_count()
    if verbose:
        print(f"Using {n_workers} workers")

    # Per-instance timeout: MILP time limit + safety margin for baseline + overhead
    per_instance_timeout = time_limit_seconds * 1.5 + 30

    from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
    
    raw_results = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(process_instance, args): i
            for i, args in enumerate(args_list)
        }

        if verbose:
            with tqdm(total=len(futures), file=sys.stdout) as pbar:
                for future in as_completed(futures, timeout=per_instance_timeout):
                    try:
                        result = future.result(timeout=1)
                        raw_results.append(result)
                    except FuturesTimeoutError:
                        idx = futures[future]
                        inst = args_list[idx][0]
                        raw_results.append(("error", inst.name, "Timeout exceeded"))
                    except Exception as e:
                        idx = futures[future]
                        inst = args_list[idx][0]
                        raw_results.append(("error", inst.name, str(e)))
                    finally:
                        pbar.update(1)
        else:
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=1)
                    raw_results.append(result)
                except Exception as e:
                    idx = futures[future]
                    inst = args_list[idx][0]
                    raw_results.append(("error", inst.name, str(e)))

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

    dataset_path = Path(__file__).parent / "RiosSolisDataset" / "Instances" / "Instances"

    if not dataset_path.exists():
        print(f"Error: Dataset path not found: {dataset_path}")
        return

    tmp_dir = Path(__file__).parent / "tmp"
    checkpoint_path = args.checkpoint or (tmp_dir / "experiment_results_checkpoint.jsonl")

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
        
        csv_path = Path(__file__).parent / "experiment_results.csv"
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
    print(f"  Multiprocessing: {'enabled' if args.parallel else 'disabled'}")
    if args.parallel:
        print(f"  Workers: {args.workers or 'auto (CPU count)'}")
    print(f"  Checkpoint: {checkpoint_path}")
    if args.restart:
        print("  Restart: yes (ignoring existing checkpoint)")
    print()

    if args.parallel:
        results = run_experiments_parallel(
            dataset_path=dataset_path,
            max_instances_per_group=args.max_instances,
            time_limit_seconds=args.time_limit,
            verbose=True,
            allowed_n_loans=tuple(args.n_loans),
            n_workers=args.workers,
            checkpoint_path=checkpoint_path,
            restart=args.restart,
        )
    else:
        results = run_experiments(
            dataset_path=dataset_path,
            max_instances_per_group=args.max_instances,
            time_limit_seconds=args.time_limit,
            verbose=True,
            allowed_n_loans=tuple(args.n_loans),
            checkpoint_path=checkpoint_path,
            restart=args.restart,
        )

    print("\n" + "=" * 60)
    print_summary(results)

    checkpoint = CheckpointManager(checkpoint_path)
    csv_path = Path(__file__).parent / "experiment_results.csv"
    checkpoint.export_to_csv(csv_path)
    if checkpoint.load_existing_results():
        print(f"\nResults exported to: {csv_path}")


if __name__ == "__main__":
    main()
