"""
Export per-instance timeline data for plotting and UI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .baseline import BaselineSolution
from .data_loader import RiosSolisInstance
from .metrics import ComparisonResult
from .milp_model import RPMLSolution


def _round_money_scalar(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _round_money_array(values: np.ndarray) -> list:
    return np.round(values.astype(float), 2).tolist()


def _loan_types(instance: RiosSolisInstance) -> list[str]:
    types: list[str] = []
    types.extend(["car"] * instance.n_cars)
    types.extend(["house"] * instance.n_houses)
    types.extend(["credit_card"] * instance.n_credit_cards)
    types.extend(["bank_loan"] * instance.n_bank_loans)
    if len(types) < instance.n:
        types.extend(["unknown"] * (instance.n - len(types)))
    return types[: instance.n]


def _algorithm_block(
    payments: np.ndarray,
    balances: np.ndarray,
    savings: np.ndarray,
    *,
    active_loans: np.ndarray | None = None,
) -> dict:
    block = {
        "paymentsByLoan": _round_money_array(payments),
        "balancesByLoan": _round_money_array(balances),
        "savingsByMonth": _round_money_array(savings),
        "totalPaymentByMonth": _round_money_array(np.sum(payments, axis=0)),
    }
    if active_loans is not None:
        block["activeLoansByMonth"] = active_loans.tolist()
    return block



def _decompose_payments(instance: RiosSolisInstance, sol) -> dict:
    principal_paid = 0.0
    interest_paid = 0.0
    penalties_paid = 0.0
    
    for j in range(instance.n):
        r_j = int(instance.release_time[j])
        p_j = float(instance.principals[j])
        final_b = float(sol.balances[j, -1])
        
        ord_int_j = 0.0
        for t in range(r_j + 1, instance.T):
            prev_b = p_j if t - 1 == r_j else float(max(0.0, sol.balances[j, t-1]))
            ord_int_j += prev_b * float(instance.interest_rates[j, t])
            
        total_x = float(np.sum(sol.payments[j, :]))
        pen_j = total_x - (p_j - final_b) - ord_int_j
        
        principal_paid += (p_j - final_b)
        interest_paid += ord_int_j
        penalties_paid += max(0.0, pen_j)
        
    return {
        "principal": _round_money_scalar(principal_paid),
        "interest": _round_money_scalar(interest_paid),
        "penalties": _round_money_scalar(penalties_paid),
    }

def build_timeline_payload(
    *,
    instance: RiosSolisInstance,
    comparison: ComparisonResult,
    optimal_solution: RPMLSolution,
    avalanche_solution: BaselineSolution,
    snowball_solution: BaselineSolution,
) -> dict:
    """
    Build JSON-serializable payload with monthly trajectories for one instance.
    """
    return {
        "schemaVersion": 1,
        "exportedAtUtc": datetime.now(timezone.utc).isoformat(),
        "instance": {
            "name": instance.name,
            "nLoans": int(instance.n),
            "horizonMonths": int(instance.T),
            "loanTypeCounts": {
                "cars": int(instance.n_cars),
                "houses": int(instance.n_houses),
                "creditCards": int(instance.n_credit_cards),
                "bankLoans": int(instance.n_bank_loans),
            },
            "loanTypes": _loan_types(instance),
            "releaseTimeByLoan": instance.release_time.tolist(),
            "monthlyIncome": _round_money_array(instance.monthly_income),
            "principals": _round_money_array(instance.principals),
            "fixedPayment": _round_money_array(instance.fixed_payment),
            "minPaymentPct": _round_money_array(instance.min_payment_pct),
            "prepayPenalty": _round_money_array(instance.prepay_penalty),
            "stipulatedAmount": _round_money_array(instance.stipulated_amount),
        },
        "summary": {
            "milp": {
                "status": comparison.optimal_status,
                "objectiveCost": _round_money_scalar(comparison.optimal_cost),
                "solveTimeSec": float(comparison.optimal_solve_time),
                "gapPct": float(comparison.optimal_gap),
                "costDecomposition": _decompose_payments(instance, optimal_solution) if comparison.optimal_status in ("OPTIMAL", "FEASIBLE") else None,
            },
            "avalanche": {
                "totalCost": _round_money_scalar(comparison.avalanche_cost),
                "valid": bool(comparison.avalanche_valid),
                "feasibleByHorizon": bool(comparison.avalanche_feasible),
                "finalBalance": _round_money_scalar(comparison.avalanche_final_balance),
                "horizonSpendAdvantagePct": _round_money_scalar(comparison.avalanche_horizon_spend_advantage),
                "repaidOnlySavingsPct": _round_money_scalar(comparison.avalanche_savings),
                "costDecomposition": _decompose_payments(instance, avalanche_solution),
            },
            "snowball": {
                "totalCost": _round_money_scalar(comparison.snowball_cost),
                "valid": bool(comparison.snowball_valid),
                "feasibleByHorizon": bool(comparison.snowball_feasible),
                "finalBalance": _round_money_scalar(comparison.snowball_final_balance),
                "horizonSpendAdvantagePct": _round_money_scalar(comparison.snowball_horizon_spend_advantage),
                "repaidOnlySavingsPct": _round_money_scalar(comparison.snowball_savings),
                "costDecomposition": _decompose_payments(instance, snowball_solution),
            },
        },
        "algorithms": {
            "milp": _algorithm_block(
                optimal_solution.payments,
                optimal_solution.balances,
                optimal_solution.savings,
                active_loans=optimal_solution.active_loans,
            ),
            "avalanche": _algorithm_block(
                avalanche_solution.payments,
                avalanche_solution.balances,
                avalanche_solution.savings,
            ),
            "snowball": _algorithm_block(
                snowball_solution.payments,
                snowball_solution.balances,
                snowball_solution.savings,
            ),
        },
    }


def export_timeline_json(
    *,
    output_dir: Path | str,
    instance: RiosSolisInstance,
    comparison: ComparisonResult,
    optimal_solution: RPMLSolution,
    avalanche_solution: BaselineSolution,
    snowball_solution: BaselineSolution,
) -> Path:
    """
    Save one instance payload as JSON and return saved path.
    """
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{instance.name}.json"
    payload = build_timeline_payload(
        instance=instance,
        comparison=comparison,
        optimal_solution=optimal_solution,
        avalanche_solution=avalanche_solution,
        snowball_solution=snowball_solution,
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path
