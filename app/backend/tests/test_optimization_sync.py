import math

import numpy as np
from rpml.milp_model import RPMLSolution
from rpml.income_monte_carlo import IncomeMCConfig
from sqlalchemy import select

from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.services.dataset_instances import list_dataset_instances


def _dataset_instance_name() -> str:
    items = list_dataset_instances()
    assert items
    return items[0].name


def test_sync_optimization_returns_plan(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    body = res.json()
    assert "total_cost" in body
    assert "payments_matrix" in body
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert math.isfinite(body["total_cost"])
    assert body["input_mode"] == "scenario_snapshot"
    assert isinstance(body["assumptions"], list)
    assert len(body["assumptions"]) >= 1
    assert isinstance(body["debts"], list)
    assert len(body["debts"]) == 2
    assert isinstance(body["savings_vector"], list)
    assert body["budget_policy"] == "starts_next_month_with_carryover"
    assert isinstance(body["budget_trace"], list)


def test_budget_trace_starts_income_from_next_month(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    trace = res.json()["budget_trace"]
    assert len(trace) == 12
    assert trace[0]["month"] == 1
    assert trace[0]["income_in"] == 0.0
    assert trace[0]["reserve_start"] == 0.0
    assert trace[1]["month"] == 2
    assert trace[1]["income_in"] == 5000.0


def test_strategy_results_include_budget_trace_for_each_strategy(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    strategies = res.json()["baseline_comparison"]["strategy_results"]
    for key in ("milp", "avalanche", "snowball"):
        assert isinstance(strategies[key]["budget_trace"], list)
        assert len(strategies[key]["budget_trace"]) == 12
        assert "implied_penalty" in strategies[key]["budget_trace"][0]


def test_optimization_no_debts_returns_400(client, auth_headers):
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "No debts to optimize"


def test_payments_matrix_shape_matches_debts_and_horizon(client, auth_headers, seeded_debts):
    horizon = 12
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": horizon},
    )
    assert res.status_code == 200
    matrix = res.json()["payments_matrix"]
    assert len(matrix) == 2
    for row in matrix:
        assert len(row) == horizon


def test_solver_failure_returns_422_without_infinity_success(client, auth_headers, seeded_debts, monkeypatch):
    def fake_run(self, instance, *, time_limit_seconds=None, ru_mode=True):
        n, t = instance.n, instance.T
        return RPMLSolution(
            payments=np.zeros((n, t)),
            balances=np.zeros((n, t)),
            savings=np.zeros(t),
            active_loans=np.zeros((n, t)),
            objective_value=float("inf"),
            solve_time=0.0,
            gap=0.0,
            status="INFEASIBLE",
        )

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync.RpmlAdapter.run",
        fake_run,
    )

    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 422
    payload = res.json()
    assert payload["detail"]["solver_status"] == "INFEASIBLE"
    assert "total_cost" not in payload
    assert not any(
        isinstance(v, float) and not math.isfinite(v) for v in _flatten_json(payload)
    )


def test_sync_optimization_accepts_debts_created_out_of_canonical_type_order(
    client,
    auth_headers,
    db_session,
    demo_user,
):
    db_session.add(
        DebtORM(
            user_id=demo_user.id,
            name="bank_first",
            loan_type="bank_loan",
            principal=2000.0,
            fixed_payment=200.0,
            min_payment_pct=0.08,
            prepay_penalty=0.0,
            interest_rate_monthly=0.01,
            default_rate_monthly=0.02,
            stipulated_amount=150.0,
            release_time=0,
        )
    )
    db_session.add(
        DebtORM(
            user_id=demo_user.id,
            name="car_second",
            loan_type="car_loan",
            principal=1000.0,
            fixed_payment=120.0,
            min_payment_pct=0.05,
            prepay_penalty=0.0,
            interest_rate_monthly=0.01,
            default_rate_monthly=0.02,
            stipulated_amount=90.0,
            release_time=0,
        )
    )
    db_session.add(
        ScenarioProfileORM(
            user_id=demo_user.id,
            code="manual",
            horizon_months=12,
            monthly_income_vector=[5000.0] * 12,
            source_json=None,
            baseline_reference={"origin": "manual"},
        )
    )
    db_session.commit()

    list_res = client.get("/api/v1/debts", headers=auth_headers)
    assert list_res.status_code == 200
    assert [row["name"] for row in list_res.json()] == ["car_second", "bank_first"]

    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    assert res.json()["status"] in ("OPTIMAL", "FEASIBLE")


def test_monte_carlo_defaults_endpoint_returns_expected_defaults(client, auth_headers):
    res = client.get("/api/v1/optimization/mc-config/defaults", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["n_scenarios"] == 16
    assert body["seed"] == 42
    assert body["rho"] == 0.55
    assert body["sigma"] == 0.15


def test_dataset_instances_catalog_returns_real_bundled_instances(client, auth_headers):
    res = client.get("/api/v1/optimization/instances", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
    first = body["items"][0]
    assert first["name"]
    assert first["loans_count"] in (4, 8, 12)
    assert first["horizon_months"] in (120, 300)


def test_sync_optimization_runs_real_dataset_instance_without_user_snapshot(client, auth_headers):
    instance_name = _dataset_instance_name()
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={
            "input_mode": "dataset_instance",
            "instance_name": instance_name,
            "ru_mode": True,
            "mc_income": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert body["input_mode"] == "dataset_instance"
    assert body["instance_name"] == instance_name
    assert body["horizon_months"] in (120, 300)
    assert isinstance(body["assumptions"], list)
    assert isinstance(body["debts"], list)
    assert len(body["debts"]) == len(body["payments_matrix"])
    assert "total_cost" in body


def test_sync_optimization_dataset_instance_rejects_horizon_override(client, auth_headers):
    instance_name = _dataset_instance_name()
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={
            "input_mode": "dataset_instance",
            "instance_name": instance_name,
            "horizon_months": 12,
        },
    )
    assert res.status_code == 400
    assert "must match the dataset instance horizon" in res.json()["detail"]


def test_sync_optimization_accepts_custom_mc_config(
    client,
    auth_headers,
    seeded_debts,
    monkeypatch,
):
    captured: list[IncomeMCConfig] = []

    def fake_mc(instance, *, ru_mode, config=None):
        assert instance is not None
        assert ru_mode is True
        assert isinstance(config, IncomeMCConfig)
        captured.append(config)
        return {
            "n_scenarios": config.n_scenarios,
            "feasible_scenarios": config.n_scenarios,
            "infeasible_rate": 0.0,
            "mean_total_cost": 123.0,
            "median_total_cost": 120.0,
            "p90_total_cost": 140.0,
            "mean_solve_time": 0.01,
            "p90_solve_time": 0.02,
        }

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync._build_monte_carlo_summary",
        fake_mc,
    )

    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={
            "horizon_months": 12,
            "ru_mode": True,
            "mc_income": True,
            "mc_config": {
                "n_scenarios": 5,
                "seed": 7,
                "rho": 0.2,
                "sigma": 0.05,
                "shock_prob": 0.1,
                "shock_severity_mean": 0.25,
                "shock_severity_std": 0.05,
                "min_income_floor": 100.0,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mc_income"] is True
    assert body["mc_config"]["n_scenarios"] == 5
    assert body["mc_config"]["seed"] == 7
    assert body["mc_summary"]["n_scenarios"] == 5
    assert captured
    assert captured[0].n_scenarios == 5
    assert captured[0].sigma == 0.05


def test_sync_optimization_uses_ru_mode_true_by_default(client, auth_headers, seeded_debts, monkeypatch):
    captured: list[bool] = []

    def fake_run(self, instance, *, time_limit_seconds=None, ru_mode=True):
        captured.append(bool(ru_mode))
        n, t = instance.n, instance.T
        return RPMLSolution(
            payments=np.zeros((n, t)),
            balances=np.zeros((n, t)),
            savings=np.zeros(t),
            active_loans=np.zeros((n, t)),
            objective_value=0.0,
            solve_time=0.0,
            gap=0.0,
            status="OPTIMAL",
        )

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync.RpmlAdapter.run",
        fake_run,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    assert captured
    assert captured[0] is True
    assert res.json()["ru_mode"] is True


def test_sync_optimization_allows_disabling_ru_mode(client, auth_headers, seeded_debts, monkeypatch):
    captured: list[bool] = []

    def fake_run(self, instance, *, time_limit_seconds=None, ru_mode=True):
        captured.append(bool(ru_mode))
        n, t = instance.n, instance.T
        return RPMLSolution(
            payments=np.zeros((n, t)),
            balances=np.zeros((n, t)),
            savings=np.zeros(t),
            active_loans=np.zeros((n, t)),
            objective_value=0.0,
            solve_time=0.0,
            gap=0.0,
            status="OPTIMAL",
        )

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync.RpmlAdapter.run",
        fake_run,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12, "ru_mode": False},
    )
    assert res.status_code == 200
    assert captured
    assert captured[0] is False
    assert res.json()["ru_mode"] is False


def test_sync_optimization_returns_mc_summary_when_enabled(client, auth_headers, seeded_debts, monkeypatch):
    summary = {
        "n_scenarios": 16,
        "feasible_scenarios": 16,
        "infeasible_rate": 0.0,
        "mean_total_cost": 100.0,
        "median_total_cost": 100.0,
        "p90_total_cost": 110.0,
        "mean_solve_time": 0.01,
        "p90_solve_time": 0.02,
    }

    def fake_mc(instance, *, ru_mode, config=None):
        assert config is not None
        return summary

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync._build_monte_carlo_summary",
        fake_mc,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12, "mc_income": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mc_income"] is True
    assert body["mc_summary"] == summary


def test_sync_optimization_normalizes_numeric_noise_in_matrices(client, auth_headers, seeded_debts, monkeypatch):
    def fake_run(self, instance, *, time_limit_seconds=None, ru_mode=True):
        n, t = instance.n, instance.T
        payments = np.zeros((n, t), dtype=float)
        balances = np.zeros((n, t), dtype=float)
        payments[0, 1] = -1e-12
        balances[1, 2] = 9e-13
        return RPMLSolution(
            payments=payments,
            balances=balances,
            savings=np.zeros(t),
            active_loans=np.zeros((n, t)),
            objective_value=1.0,
            solve_time=0.0,
            gap=0.0,
            status="OPTIMAL",
        )

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync.RpmlAdapter.run",
        fake_run,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["payments_matrix"][0][1] == 0.0
    assert body["balances_matrix"][1][2] == 0.0
    assert body["baseline_comparison"]["strategy_results"]["milp"]["payments_matrix"][0][1] == 0.0


def test_budget_trace_exposes_implied_reserve_from_plan(client, auth_headers, seeded_debts, monkeypatch):
    def fake_run(self, instance, *, time_limit_seconds=None, ru_mode=True):
        n, t = instance.n, instance.T
        payments = np.zeros((n, t), dtype=float)
        balances = np.zeros((n, t), dtype=float)
        if t >= 2:
            payments[:, 1] = [50.0] * n
        return RPMLSolution(
            payments=payments,
            balances=balances,
            savings=np.zeros(t, dtype=float),
            active_loans=np.zeros((n, t)),
            objective_value=float(np.sum(payments)),
            solve_time=0.0,
            gap=0.0,
            status="OPTIMAL",
        )

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync.RpmlAdapter.run",
        fake_run,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["savings_vector"][1] == 4900.0
    assert body["budget_trace"][1]["reserve_end"] == 4900.0
    assert body["budget_trace"][1]["carry_out"] == 4900.0


def test_budget_trace_exposes_implied_penalty_from_balance_dynamics(
    client,
    auth_headers,
    seeded_debts,
    monkeypatch,
):
    def fake_run(self, instance, *, time_limit_seconds=None, ru_mode=True):
        n, t = instance.n, instance.T
        payments = np.zeros((n, t), dtype=float)
        balances = np.zeros((n, t), dtype=float)
        if t >= 2:
            rate = float(instance.interest_rates[0, 1])
            payments[0, 1] = 10.0
            balances[0, 0] = 100.0
            balances[0, 1] = 95.0 + 100.0 * rate
        return RPMLSolution(
            payments=payments,
            balances=balances,
            savings=np.zeros(t, dtype=float),
            active_loans=np.zeros((n, t)),
            objective_value=float(np.sum(payments)),
            solve_time=0.0,
            gap=0.0,
            status="OPTIMAL",
        )

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync.RpmlAdapter.run",
        fake_run,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["budget_trace"][1]["implied_penalty"] == 5.0
    milp_trace = body["baseline_comparison"]["strategy_results"]["milp"]["budget_trace"]
    assert milp_trace[1]["implied_penalty"] == 5.0


def test_sync_optimization_ignores_stale_source_json_lengths(client, auth_headers, seeded_debts, db_session):
    profile = db_session.scalar(select(ScenarioProfileORM))
    assert profile is not None
    assert isinstance(profile.source_json, dict)
    profile.source_json["principals"] = [1000.0, 2000.0, 3000.0, 4000.0]
    db_session.add(profile)
    db_session.commit()

    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert "total_cost" in body


def _flatten_json(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten_json(v)
    else:
        yield obj
