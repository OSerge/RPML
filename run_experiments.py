"""
Run experiments on Rios-Solis dataset.

Compares optimal MILP solutions with baseline strategies.
"""

import argparse
from pathlib import Path
from typing import List

import numpy as np
from tqdm import tqdm

from rpml.data_loader import load_all_instances, get_instances_by_size
from rpml.milp_model import solve_rpml
from rpml.baseline import debt_avalanche
from rpml.metrics import compare_solutions, print_summary, ComparisonResult


def run_experiments(
    dataset_path: Path,
    max_instances_per_group: int = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
) -> List[ComparisonResult]:
    """
    Run experiments on all instances.
    
    Args:
        dataset_path: Path to directory containing .dat files
        max_instances_per_group: Maximum instances to process per group (None = all)
        time_limit_seconds: Time limit for MILP solver
        verbose: Print progress
        allowed_n_loans: Process only instances with these loan counts
    
    Returns:
        List of ComparisonResult objects
    """
    if verbose:
        print("Loading instances...")
    
    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)
    
    if verbose:
        print(f"Loaded {len(instances)} instances")
        for n, group in grouped.items():
            print(f"  {n} loans: {len(group)} instances")
    
    results = []
    
    # Process each group
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])
        
        if not group_instances:
            continue
        
        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]
        
        if verbose:
            print(f"\nProcessing {n_loans}-loan instances ({len(group_instances)} instances)...")
        
        iterator = tqdm(group_instances) if verbose else group_instances
        
        for instance in iterator:
            try:
                # Solve optimal MILP
                optimal_solution = solve_rpml(instance, time_limit_seconds=time_limit_seconds)
                
                # Skip if not optimal or feasible
                if optimal_solution.status not in ["OPTIMAL", "FEASIBLE"]:
                    if verbose:
                        print(f"\nWarning: {instance.name} status: {optimal_solution.status}")
                    continue
                
                # Solve baseline (Debt Avalanche)
                baseline_solution = debt_avalanche(instance)
                
                # Only compare if baseline also achieves near-zero final balance
                # (i.e., baseline can actually pay off all debts)
                max_final_balance = np.max(np.abs(baseline_solution.balances[:, -1]))
                if max_final_balance > 1e6:  # Skip if any loan has >1M remaining
                    if verbose:
                        tqdm.write(f"  Skipping {instance.name}: baseline can't pay off (max balance: {max_final_balance:,.0f})")
                    continue
                
                # Compare
                comparison = compare_solutions(
                    optimal=optimal_solution,
                    baseline=baseline_solution,
                    instance_name=instance.name,
                    n_loans=n_loans,
                )
                
                results.append(comparison)
                
            except Exception as e:
                if verbose:
                    print(f"\nError processing {instance.name}: {e}")
                continue
    
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
    
    return parser.parse_args()


def process_instance(args_tuple):
    """Process a single instance (for multiprocessing)."""
    instance, time_limit_seconds, verbose = args_tuple
    
    try:
        # Solve optimal MILP
        optimal_solution = solve_rpml(instance, time_limit_seconds=time_limit_seconds)
        
        # Skip if not optimal or feasible
        if optimal_solution.status not in ["OPTIMAL", "FEASIBLE"]:
            return ("skip_status", instance.name, optimal_solution.status)
        
        # Solve baseline (Debt Avalanche)
        baseline_solution = debt_avalanche(instance)
        
        # Only compare if baseline also achieves near-zero final balance
        max_final_balance = np.max(np.abs(baseline_solution.balances[:, -1]))
        if max_final_balance > 1e6:
            return ("skip_balance", instance.name, max_final_balance)
        
        # Compare
        comparison = compare_solutions(
            optimal=optimal_solution,
            baseline=baseline_solution,
            instance_name=instance.name,
            n_loans=instance.n,
        )
        
        return ("ok", comparison)
        
    except Exception as e:
        return ("error", instance.name, str(e))


def run_experiments_parallel(
    dataset_path: Path,
    max_instances_per_group: int = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    n_workers: int = None,
) -> List[ComparisonResult]:
    """
    Run experiments on all instances using multiprocessing.
    
    Args:
        dataset_path: Path to directory containing .dat files
        max_instances_per_group: Maximum instances to process per group (None = all)
        time_limit_seconds: Time limit for MILP solver
        verbose: Print progress
        allowed_n_loans: Process only instances with these loan counts
        n_workers: Number of parallel workers (None = CPU count)
    
    Returns:
        List of ComparisonResult objects
    """
    from multiprocessing import Pool, cpu_count
    
    if verbose:
        print("Loading instances...")
    
    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)
    
    if verbose:
        print(f"Loaded {len(instances)} instances")
        for n, group in grouped.items():
            print(f"  {n} loans: {len(group)} instances")
    
    # Collect all instances to process
    all_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])
        
        if not group_instances:
            continue
        
        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]
        
        all_instances.extend(group_instances)
    
    if verbose:
        print(f"\nProcessing {len(all_instances)} instances in parallel...")
    
    # Prepare arguments for multiprocessing
    args_list = [(inst, time_limit_seconds, False) for inst in all_instances]
    
    # Run in parallel
    n_workers = n_workers or cpu_count()
    if verbose:
        print(f"Using {n_workers} workers")
    
    with Pool(n_workers) as pool:
        if verbose:
            raw_results = list(tqdm(
                pool.imap(process_instance, args_list),
                total=len(args_list),
            ))
        else:
            raw_results = list(pool.imap(process_instance, args_list))
    
    # Process results and report issues
    results = []
    for r in raw_results:
        if r is None:
            continue
        if r[0] == "ok":
            results.append(r[1])
        elif r[0] == "skip_status" and verbose:
            print(f"  Skipped {r[1]}: status {r[2]}")
        elif r[0] == "skip_balance" and verbose:
            print(f"  Skipped {r[1]}: baseline can't pay off (max balance: {r[2]:,.0f})")
        elif r[0] == "error" and verbose:
            print(f"  Error {r[1]}: {r[2]}")
    
    return results


def main():
    """Main entry point."""
    args = parse_args()
    
    dataset_path = Path(__file__).parent / "RiosSolisDataset" / "Instances" / "Instances"
    
    if not dataset_path.exists():
        print(f"Error: Dataset path not found: {dataset_path}")
        return
    
    print("=" * 60)
    print("RPML EXPERIMENTS")
    print("=" * 60)
    print("\nRunning experiments on Rios-Solis dataset...")
    print("Comparing optimal MILP solutions with Debt Avalanche baseline.")
    print(f"\nParameters:")
    print(f"  Max instances per group: {args.max_instances or 'all'}")
    print(f"  Loan counts: {args.n_loans}")
    print(f"  Time limit: {args.time_limit}s")
    print(f"  Multiprocessing: {'enabled' if args.parallel else 'disabled'}")
    if args.parallel:
        print(f"  Workers: {args.workers or 'auto (CPU count)'}")
    print()
    
    # Run experiments
    if args.parallel:
        results = run_experiments_parallel(
            dataset_path=dataset_path,
            max_instances_per_group=args.max_instances,
            time_limit_seconds=args.time_limit,
            verbose=True,
            allowed_n_loans=tuple(args.n_loans),
            n_workers=args.workers,
        )
    else:
        results = run_experiments(
            dataset_path=dataset_path,
            max_instances_per_group=args.max_instances,
            time_limit_seconds=args.time_limit,
            verbose=True,
            allowed_n_loans=tuple(args.n_loans),
        )
    
    # Print summary
    print("\n" + "=" * 60)
    print_summary(results)
    
    # Save results
    if results:
        import pandas as pd
        
        results_df = pd.DataFrame([
            {
                'instance': r.instance_name,
                'n_loans': r.n_loans,
                'optimal_cost': r.optimal_cost,
                'baseline_cost': r.baseline_cost,
                'savings_pct': r.relative_savings,
                'solve_time': r.optimal_solve_time,
                'gap': r.optimal_gap,
                'status': r.optimal_status,
            }
            for r in results
        ])
        
        output_path = Path(__file__).parent / "experiment_results.csv"
        results_df.to_csv(output_path, index=False)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
