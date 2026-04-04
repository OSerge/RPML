import numpy as np
import pytest

from rpml.baseline import BaselineSolution
from rpml.data_loader import RiosSolisInstance
from rpml.metrics import (
    ComparisonResult,
    aggregate_results,
    compare_solutions,
    compute_cash_shortfall_rate,
    compute_cvar,
    print_summary,
    validate_baseline_solution,
)
from rpml.milp_model import RPMLSolution


def create_instance() -> RiosSolisInstance:
    return RiosSolisInstance(
        name="metrics-status",
        n=1,
        T=2,
        n_cars=1,
        n_houses=0,
        n_credit_cards=0,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 2)),
        default_rates=np.zeros((1, 2)),
        min_payment_pct=np.array([0.0]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([60.0, 60.0]),
        release_time=np.array([0]),
        stipulated_amount=np.array([0.0]),
        fixed_payment=np.array([0.0]),
    )


def test_validate_baseline_distinguishes_validity_from_repayment():
    instance = create_instance()
    solution = BaselineSolution(
        payments=np.array([[0.0, 80.0]]),
        balances=np.array([[100.0, 20.0]]),
        savings=np.array([60.0, 40.0]),
        total_cost=80.0,
        strategy_name="Test",
    )

    is_valid, errors, final_balance = validate_baseline_solution(solution, instance)

    assert is_valid is True
    assert errors == []
    assert final_balance == 20.0


def test_compare_solutions_keeps_horizon_advantage_for_unrepaid_baseline():
    optimal = RPMLSolution(
        payments=np.array([[0.0, 100.0]]),
        balances=np.array([[50.0, 0.0]]),
        savings=np.array([60.0, 20.0]),
        active_loans=np.array([[1.0, 1.0]]),
        objective_value=100.0,
        solve_time=1.0,
        gap=0.0,
        status="OPTIMAL",
    )
    avalanche = BaselineSolution(
        payments=np.array([[0.0, 100.0]]),
        balances=np.array([[50.0, 10.0]]),
        savings=np.array([60.0, 20.0]),
        total_cost=100.0,
        strategy_name="Avalanche",
    )
    snowball = BaselineSolution(
        payments=np.array([[0.0, 120.0]]),
        balances=np.array([[40.0, 0.0]]),
        savings=np.array([60.0, 0.0]),
        total_cost=120.0,
        strategy_name="Snowball",
    )

    result = compare_solutions(
        optimal=optimal,
        avalanche=avalanche,
        snowball=snowball,
        instance_name="metrics-status",
        n_loans=1,
        avalanche_valid=True,
        avalanche_repaid_by_T=False,
        avalanche_final_balance=10.0,
        snowball_valid=True,
        snowball_repaid_by_T=True,
        snowball_final_balance=0.0,
    )

    assert result.avalanche_valid is True
    assert result.avalanche_feasible is False
    assert result.avalanche_final_balance == 10.0
    assert result.avalanche_horizon_spend_advantage == 0.0
    assert result.avalanche_savings is None

    assert result.snowball_valid is True
    assert result.snowball_feasible is True
    assert result.snowball_final_balance == 0.0
    assert result.snowball_horizon_spend_advantage == pytest.approx(100.0 / 6.0)
    assert result.snowball_savings == pytest.approx(100.0 / 6.0)


def test_aggregate_results_separates_optimal_and_feasible_metrics():
    results = [
        ComparisonResult(
            instance_name="opt-1",
            n_loans=4,
            optimal_cost=95.0,
            optimal_solve_time=10.0,
            optimal_gap=0.0,
            optimal_status="OPTIMAL",
            avalanche_cost=100.0,
            avalanche_valid=True,
            avalanche_feasible=True,
            avalanche_final_balance=0.0,
            avalanche_horizon_spend_advantage=5.0,
            avalanche_savings=5.0,
            snowball_cost=110.0,
            snowball_valid=True,
            snowball_feasible=True,
            snowball_final_balance=0.0,
            snowball_horizon_spend_advantage=10.0,
            snowball_savings=10.0,
        ),
        ComparisonResult(
            instance_name="feas-1",
            n_loans=4,
            optimal_cost=102.0,
            optimal_solve_time=20.0,
            optimal_gap=2.0,
            optimal_status="FEASIBLE",
            avalanche_cost=100.0,
            avalanche_valid=True,
            avalanche_feasible=False,
            avalanche_final_balance=5.0,
            avalanche_horizon_spend_advantage=-2.0,
            avalanche_savings=None,
            snowball_cost=108.0,
            snowball_valid=True,
            snowball_feasible=True,
            snowball_final_balance=0.0,
            snowball_horizon_spend_advantage=5.0,
            snowball_savings=5.0,
        ),
    ]

    agg = aggregate_results(results)

    assert agg["status_counts"] == {"OPTIMAL": 1, "FEASIBLE": 1}
    assert agg["avalanche"]["all_horizon"]["avg"] == pytest.approx(1.5)
    assert agg["avalanche"]["optimal_only_horizon"]["avg"] == pytest.approx(5.0)
    assert agg["avalanche"]["feasible_only_horizon"]["avg"] == pytest.approx(-2.0)
    assert agg["snowball"]["all_horizon"]["avg"] == pytest.approx(7.5)
    assert agg["snowball"]["optimal_only_horizon"]["avg"] == pytest.approx(10.0)
    assert agg["snowball"]["feasible_only_horizon"]["avg"] == pytest.approx(5.0)
    assert agg["optimal_count"] == 1
    assert agg["usable_count"] == 2
    assert agg["solve_stats"]["median_solve_time"] == pytest.approx(15.0)
    assert agg["solve_stats"]["p90_solve_time"] == pytest.approx(19.0)
    assert agg["feasible_instances"] == [
        {"instance_name": "feas-1", "solve_time": 20.0, "gap": 2.0}
    ]
    assert agg["not_solved_instances"] == []
    assert agg["by_n_loans"][4]["status_counts"] == {"OPTIMAL": 1, "FEASIBLE": 1}
    assert agg["by_n_loans"][4]["slowest_instances"][0]["instance_name"] == "feas-1"


def test_print_summary_reports_status_split(capsys):
    results = [
        ComparisonResult(
            instance_name="opt-1",
            n_loans=8,
            optimal_cost=95.0,
            optimal_solve_time=12.0,
            optimal_gap=0.0,
            optimal_status="OPTIMAL",
            avalanche_cost=100.0,
            avalanche_valid=True,
            avalanche_feasible=True,
            avalanche_final_balance=0.0,
            avalanche_horizon_spend_advantage=5.0,
            avalanche_savings=5.0,
            snowball_cost=110.0,
            snowball_valid=True,
            snowball_feasible=True,
            snowball_final_balance=0.0,
            snowball_horizon_spend_advantage=10.0,
            snowball_savings=10.0,
        ),
        ComparisonResult(
            instance_name="feas-1",
            n_loans=8,
            optimal_cost=102.0,
            optimal_solve_time=24.0,
            optimal_gap=2.0,
            optimal_status="FEASIBLE",
            avalanche_cost=100.0,
            avalanche_valid=True,
            avalanche_feasible=False,
            avalanche_final_balance=5.0,
            avalanche_horizon_spend_advantage=-2.0,
            avalanche_savings=None,
            snowball_cost=108.0,
            snowball_valid=True,
            snowball_feasible=True,
            snowball_final_balance=0.0,
            snowball_horizon_spend_advantage=5.0,
            snowball_savings=5.0,
        ),
    ]

    print_summary(results)
    out = capsys.readouterr().out

    assert "MILP statuses: OPTIMAL 1, FEASIBLE 1" in out
    assert "OPTIMAL coverage: 1/2 (50.0%)" in out
    assert "Usable coverage (OPTIMAL+FEASIBLE): 2/2 (100.0%)" in out
    assert "Solve time: avg 18.00s, median 18.00s, p90 22.80s, max 24.00s" in out
    assert "All comparable (OPTIMAL+FEASIBLE): avg 1.50%" in out
    assert "OPTIMAL-only horizon advantage: avg 5.00%" in out
    assert "FEASIBLE-only horizon advantage: avg -2.00%" in out
    assert "8 loans" in out
    assert "Problem cases:" in out
    assert "FEASIBLE instances: feas-1 (24.00s, gap 2.00%)" in out


def test_compute_cvar_matches_manual_tail_average():
    samples = np.array([0.0, 1.0, 2.0, 3.0, 10.0], dtype=float)
    cvar = compute_cvar(samples, alpha=0.8)

    # VaR_0.8 = 3.0 => tail = [3.0, 10.0], mean = 6.5
    assert cvar == pytest.approx(6.5)


def test_compute_cash_shortfall_rate_counts_positive_events():
    shortfalls = np.array([0.0, 0.0, 1e-7, 0.02, 1.5], dtype=float)
    rate = compute_cash_shortfall_rate(shortfalls, epsilon=1e-6)

    assert rate == pytest.approx(2 / 5)
