"""
Run experiments on Rios-Solis dataset.

Compares optimal MILP solutions with baseline strategies.
"""

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


def main():
    """Main entry point."""
    dataset_path = Path(__file__).parent / "RiosSolisDataset" / "Instances" / "Instances"
    
    if not dataset_path.exists():
        print(f"Error: Dataset path not found: {dataset_path}")
        return
    
    print("=" * 60)
    print("RPML EXPERIMENTS")
    print("=" * 60)
    print("\nRunning experiments on Rios-Solis dataset...")
    print("Comparing optimal MILP solutions with Debt Avalanche baseline.\n")
    
    # Run experiments
    # Limit to 10 instances per group for initial testing
    # Remove max_instances_per_group to run on all 550 instances
    results = run_experiments(
        dataset_path=dataset_path,
        max_instances_per_group=30,  # Set to None for full dataset
        time_limit_seconds=300,
        verbose=True,
        allowed_n_loans=(4, 8, 12),
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
