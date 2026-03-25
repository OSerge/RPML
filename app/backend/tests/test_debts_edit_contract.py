def test_debts_get_and_patch_core_fields(client, auth_headers, seeded_debts):
    create = client.post(
        "/api/v1/debts",
        headers=auth_headers,
        json={
            "name": "editable_loan",
            "loan_type": "bank_loan",
            "principal": 3200.0,
            "fixed_payment": 210.0,
            "min_payment_pct": 0.08,
            "prepay_penalty": 0.0,
            "interest_rate_monthly": 0.013,
            "default_rate_monthly": 0.05,
            "stipulated_amount": 90.0,
            "release_time": 0,
        },
    )
    assert create.status_code == 201
    debt = create.json()
    debt_id = debt["id"]
    assert debt["principal"] == 3200.0
    assert debt["interest_rate_monthly"] == 0.013

    update = client.patch(
        f"/api/v1/debts/{debt_id}",
        headers=auth_headers,
        json={
            "fixed_payment": 250.0,
            "min_payment_pct": 0.09,
            "name": "editable_loan_v2",
        },
    )
    assert update.status_code == 200
    body = update.json()
    assert body["name"] == "editable_loan_v2"
    assert body["fixed_payment"] == 250.0
    assert body["min_payment_pct"] == 0.09

    rows = client.get("/api/v1/debts", headers=auth_headers)
    assert rows.status_code == 200
    found = [d for d in rows.json() if d["id"] == debt_id]
    assert len(found) == 1
    assert found[0]["release_time"] == 0
