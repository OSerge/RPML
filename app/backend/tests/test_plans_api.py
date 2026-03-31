import uuid


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
    assert "payments_matrix" in body
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
