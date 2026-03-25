import math

import numpy as np
from rpml.milp_model import RPMLSolution


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
    def fake_run(self, instance, *, time_limit_seconds=None):
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


def _flatten_json(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten_json(v)
    else:
        yield obj
