import json

import numpy as np

from rpml.baseline import BaselineSolution
from rpml.data_loader import RiosSolisInstance
from rpml.metrics import compare_solutions
from rpml.milp_model import RPMLSolution
from rpml.timeline_export import build_timeline_payload, export_timeline_json


def _sample_instance() -> RiosSolisInstance:
    return RiosSolisInstance(
        name="inst_demo",
        n=2,
        T=3,
        n_cars=1,
        n_houses=0,
        n_credit_cards=1,
        n_bank_loans=0,
        principals=np.array([100.0, 150.0]),
        interest_rates=np.zeros((2, 3)),
        default_rates=np.zeros((2, 3)),
        min_payment_pct=np.array([0.1, 0.1]),
        prepay_penalty=np.array([0.0, 0.0]),
        monthly_income=np.array([120.0, 120.0, 120.0]),
        release_time=np.array([0, 1]),
        stipulated_amount=np.array([30.0, 20.0]),
        fixed_payment=np.array([30.0, 20.0]),
    )


def _sample_solutions():
    milp = RPMLSolution(
        payments=np.array([[0.0, 50.129, 50.0], [0.0, 0.0, 100.005]]),
        balances=np.array([[100.0, 50.0, 0.0], [0.0, 150.0, 50.678]]),
        savings=np.array([120.0, 70.333, 20.0]),
        active_loans=np.array([[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]]),
        objective_value=200.1234,
        solve_time=0.42,
        gap=0.01,
        status="FEASIBLE",
    )
    avalanche = BaselineSolution(
        payments=np.array([[0.0, 60.0, 40.0], [0.0, 0.0, 110.0]]),
        balances=np.array([[100.0, 40.0, 0.0], [0.0, 150.0, 40.0]]),
        savings=np.array([120.0, 60.0, 10.0]),
        total_cost=210.0,
        strategy_name="debt_avalanche",
    )
    snowball = BaselineSolution(
        payments=np.array([[0.0, 40.0, 60.0], [0.0, 0.0, 120.0]]),
        balances=np.array([[100.0, 60.0, 0.0], [0.0, 150.0, 30.0]]),
        savings=np.array([120.0, 80.0, 0.0]),
        total_cost=220.0,
        strategy_name="debt_snowball",
    )
    return milp, avalanche, snowball


def test_build_timeline_payload_shape_and_totals():
    instance = _sample_instance()
    milp, avalanche, snowball = _sample_solutions()
    comparison = compare_solutions(
        optimal=milp,
        avalanche=avalanche,
        snowball=snowball,
        instance_name=instance.name,
        n_loans=instance.n,
        avalanche_valid=True,
        avalanche_repaid_by_T=True,
        avalanche_final_balance=0.0,
        snowball_valid=True,
        snowball_repaid_by_T=True,
        snowball_final_balance=0.0,
    )

    payload = build_timeline_payload(
        instance=instance,
        comparison=comparison,
        optimal_solution=milp,
        avalanche_solution=avalanche,
        snowball_solution=snowball,
    )

    assert payload["instance"]["name"] == "inst_demo"
    assert payload["instance"]["nLoans"] == 2
    assert payload["instance"]["horizonMonths"] == 3
    assert payload["instance"]["loanTypes"] == ["car", "credit_card"]

    for algo_name in ("milp", "avalanche", "snowball"):
        block = payload["algorithms"][algo_name]
        assert len(block["paymentsByLoan"]) == 2
        assert all(len(row) == 3 for row in block["paymentsByLoan"])
        assert len(block["balancesByLoan"]) == 2
        assert all(len(row) == 3 for row in block["balancesByLoan"])
        assert len(block["savingsByMonth"]) == 3
        assert len(block["totalPaymentByMonth"]) == 3

    assert payload["algorithms"]["milp"]["activeLoansByMonth"] is not None
    assert payload["algorithms"]["milp"]["totalPaymentByMonth"] == [0.0, 50.13, 150.0]
    assert payload["algorithms"]["milp"]["savingsByMonth"] == [120.0, 70.33, 20.0]
    assert payload["summary"]["milp"]["objectiveCost"] == 200.12
    assert payload["summary"]["milp"]["status"] == "FEASIBLE"


def test_export_timeline_json_writes_expected_file(tmp_path):
    instance = _sample_instance()
    milp, avalanche, snowball = _sample_solutions()
    comparison = compare_solutions(
        optimal=milp,
        avalanche=avalanche,
        snowball=snowball,
        instance_name=instance.name,
        n_loans=instance.n,
        avalanche_valid=True,
        avalanche_repaid_by_T=True,
        avalanche_final_balance=0.0,
        snowball_valid=True,
        snowball_repaid_by_T=True,
        snowball_final_balance=0.0,
    )

    output_path = export_timeline_json(
        output_dir=tmp_path,
        instance=instance,
        comparison=comparison,
        optimal_solution=milp,
        avalanche_solution=avalanche,
        snowball_solution=snowball,
    )

    assert output_path.name == "inst_demo.json"
    assert output_path.exists()

    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["summary"]["milp"]["objectiveCost"] == 200.12
    assert data["algorithms"]["snowball"]["totalPaymentByMonth"] == [0.0, 40.0, 180.0]
