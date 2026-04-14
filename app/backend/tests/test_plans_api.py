import uuid

from server.services.dataset_instances import list_dataset_instances


def _dataset_instance_name() -> str:
    items = list_dataset_instances()
    assert items
    return items[0].name


def test_get_plan_by_id_returns_persisted_plan(client, auth_headers, seeded_debts):
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
    plan_id = status_res.json()["plan_id"]

    plan_res = client.get(
        f"/api/v1/optimization/plans/{plan_id}",
        headers=auth_headers,
    )
    assert plan_res.status_code == 200
    body = plan_res.json()
    assert "total_cost" in body
    assert "debts" in body
    assert "payments_matrix" in body
    assert "balances_matrix" in body
    assert "baseline_comparison" in body
    assert "budget_trace" in body
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert body["input_mode"] == "scenario_snapshot"
    assert isinstance(body["assumptions"], list)


def test_get_plan_unknown_returns_404(client, auth_headers):
    res = client.get(
        f"/api/v1/optimization/plans/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_get_plan_requires_auth(client):
    res = client.get(f"/api/v1/optimization/plans/{uuid.uuid4()}")
    assert res.status_code == 401


def test_get_plan_returns_dataset_instance_metadata(client, auth_headers):
    instance_name = _dataset_instance_name()
    create = client.post(
        "/api/v1/optimization/tasks",
        headers=auth_headers,
        json={
            "input_mode": "dataset_instance",
            "instance_name": instance_name,
        },
    )
    assert create.status_code == 202
    task_id = create.json()["task_id"]

    status_res = client.get(
        f"/api/v1/optimization/tasks/{task_id}",
        headers=auth_headers,
    )
    assert status_res.status_code == 200
    plan_id = status_res.json()["plan_id"]

    plan_res = client.get(
        f"/api/v1/optimization/plans/{plan_id}",
        headers=auth_headers,
    )
    assert plan_res.status_code == 200
    body = plan_res.json()
    assert body["input_mode"] == "dataset_instance"
    assert body["instance_name"] == instance_name
    assert body["horizon_months"] in (120, 300)
    assert len(body["debts"]) == len(body["payments_matrix"])
