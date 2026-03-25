def test_list_loan_types_is_public(client):
    res = client.get("/api/v1/debts/loan-types")
    assert res.status_code == 200
    body = res.json()
    assert body["supported_values"] == [
        "car_loan",
        "house_loan",
        "credit_card",
        "bank_loan",
    ]


def test_create_debt_accepts_all_rpml_loan_types(client, auth_headers):
    payloads = [
        {"name": "car debt", "loan_type": "car_loan"},
        {"name": "house debt", "loan_type": "house_loan"},
        {"name": "credit debt", "loan_type": "credit_card"},
        {"name": "bank debt", "loan_type": "bank_loan"},
    ]
    created_ids: list[int] = []
    for payload in payloads:
        res = client.post("/api/v1/debts", headers=auth_headers, json=payload)
        assert res.status_code == 201
        created = res.json()
        created_ids.append(created["id"])
        assert created["loan_type"] == payload["loan_type"]

    list_res = client.get("/api/v1/debts", headers=auth_headers)
    assert list_res.status_code == 200
    rows = {row["id"]: row for row in list_res.json()}
    assert set(created_ids).issubset(set(rows.keys()))


def test_create_debt_rejects_unsupported_loan_type(client, auth_headers):
    res = client.post(
        "/api/v1/debts",
        headers=auth_headers,
        json={"name": "bad", "loan_type": "payday"},
    )
    assert res.status_code == 422
