"""RPML: Repayment Planning for Multiple Loans optimization package."""

from .data_loader import RiosSolisInstance, load_instance, load_all_instances, get_instances_by_size
from .milp_model import solve_rpml, RPMLSolution
from .baseline import BaselineSolution, debt_avalanche, debt_snowball, debt_average
from .metrics import ComparisonResult, compare_solutions, aggregate_results, print_summary
from .checkpoint import CheckpointManager

__all__ = [
    "RiosSolisInstance",
    "load_instance",
    "load_all_instances",
    "get_instances_by_size",
    "solve_rpml",
    "RPMLSolution",
    "BaselineSolution",
    "debt_avalanche",
    "debt_snowball",
    "debt_average",
    "ComparisonResult",
    "compare_solutions",
    "aggregate_results",
    "print_summary",
    "CheckpointManager",
]

