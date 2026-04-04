"""RPML: Repayment Planning for Multiple Loans optimization package."""

from .data_loader import (
    RiosSolisInstance,
    load_instance,
    load_all_instances,
    get_instances_by_size,
    with_budget_starts_next_month,
)
from .milp_model import (
    solve_rpml,
    solve_stochastic_rpml,
    evaluate_fixed_plan_shortfalls,
    RPMLSolution,
    StochasticRPMLSolution,
)
from .baseline import BaselineSolution, debt_avalanche, debt_snowball, debt_average
from .metrics import (
    ComparisonResult,
    MonteCarloAggregateResult,
    StochasticRiskComparisonResult,
    aggregate_monte_carlo_results,
    compute_cash_shortfall_rate,
    compute_cvar,
    compare_solutions,
    aggregate_results,
    print_summary,
    print_stochastic_risk_summary,
)
from .checkpoint import CheckpointManager
from .income_monte_carlo import (
    IncomeMCConfig,
    derive_instance_seed,
    replace_instance_income,
    simulate_income_paths,
)

__all__ = [
    "RiosSolisInstance",
    "load_instance",
    "load_all_instances",
    "get_instances_by_size",
    "with_budget_starts_next_month",
    "solve_rpml",
    "solve_stochastic_rpml",
    "evaluate_fixed_plan_shortfalls",
    "RPMLSolution",
    "StochasticRPMLSolution",
    "BaselineSolution",
    "debt_avalanche",
    "debt_snowball",
    "debt_average",
    "ComparisonResult",
    "MonteCarloAggregateResult",
    "StochasticRiskComparisonResult",
    "compare_solutions",
    "aggregate_monte_carlo_results",
    "compute_cvar",
    "compute_cash_shortfall_rate",
    "aggregate_results",
    "print_summary",
    "print_stochastic_risk_summary",
    "CheckpointManager",
    "IncomeMCConfig",
    "derive_instance_seed",
    "replace_instance_income",
    "simulate_income_paths",
]

