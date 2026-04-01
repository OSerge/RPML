import math

import numpy as np
from rpml.milp_model import RPMLSolution
from sqlalchemy import select

from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM


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

    def fake_mc(instance, *, ru_mode):
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
