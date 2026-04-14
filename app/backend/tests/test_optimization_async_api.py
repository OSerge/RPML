import uuid

import pytest
from rpml.milp_model import RPMLSolution
import numpy as np

from server.services.dataset_instances import list_dataset_instances


def _dataset_instance_name() -> str:
    items = list_dataset_instances()
    assert items
    return items[0].name


def test_create_async_task_returns_task_id(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/tasks",
        headers=auth_headers,
        json={"horizon_months": 24},
    )
    assert res.status_code == 202
    body = res.json()
    assert "task_id" in body
    assert body.get("status") == "pending"
    assert body.get("ru_mode") is True
    assert body.get("mc_income") is False
    uuid.UUID(body["task_id"])


def test_create_async_task_accepts_mode_flags(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/tasks",
        headers=auth_headers,
        json={"horizon_months": 24, "ru_mode": False, "mc_income": True},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["ru_mode"] is False
    assert body["mc_income"] is True


def test_get_task_status_returns_completed_with_plan_id(client, auth_headers, seeded_debts):
    create = client.post(
        "/api/v1/optimization/tasks",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert create.status_code == 202
    task_id = create.json()["task_id"]

    status_res = client.get(
        f"/api/v1/optimization/tasks/{task_id}",
        headers=auth_headers,
    )
    assert status_res.status_code == 200
    payload = status_res.json()
    assert payload["status"] == "completed"
    assert payload["task_id"] == task_id
    assert "plan_id" in payload
    assert payload["plan_id"]
    assert payload["ru_mode"] is True
    assert payload["mc_income"] is False
    uuid.UUID(payload["plan_id"])
    assert payload.get("error") in (None, "")


def test_get_task_status_failed_shows_error(client, auth_headers, seeded_debts, monkeypatch):
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

    create = client.post(
        "/api/v1/optimization/tasks",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert create.status_code == 202
    task_id = create.json()["task_id"]

    status_res = client.get(
        f"/api/v1/optimization/tasks/{task_id}",
        headers=auth_headers,
    )
    assert status_res.status_code == 200
    body = status_res.json()
    assert body["status"] == "failed"
    assert body["task_id"] == task_id
    assert body["ru_mode"] is True
    assert body["mc_income"] is False
    assert body.get("plan_id") in (None, "")
    assert body.get("error")


def test_get_task_unknown_returns_404(client, auth_headers):
    res = client.get(
        f"/api/v1/optimization/tasks/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_create_async_task_requires_auth(client, seeded_debts):
    res = client.post(
        "/api/v1/optimization/tasks",
        json={"horizon_months": 12},
    )
    assert res.status_code == 401


def test_create_async_task_accepts_dataset_instance_without_snapshot(client, auth_headers):
    instance_name = _dataset_instance_name()
    res = client.post(
        "/api/v1/optimization/tasks",
        headers=auth_headers,
        json={
            "input_mode": "dataset_instance",
            "instance_name": instance_name,
            "ru_mode": True,
            "mc_income": False,
        },
    )
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "pending"
    assert body["input_mode"] == "dataset_instance"
    assert body["instance_name"] == instance_name
    assert body["horizon_months"] in (120, 300)

    status_res = client.get(
        f"/api/v1/optimization/tasks/{body['task_id']}",
        headers=auth_headers,
    )
    assert status_res.status_code == 200
    status_body = status_res.json()
    assert status_body["status"] == "completed"
    assert status_body["input_mode"] == "dataset_instance"
    assert status_body["instance_name"] == instance_name
