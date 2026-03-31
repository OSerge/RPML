def test_create_debt_requires_auth(client):
    res = client.post("/api/v1/debts", json={"name": "loan", "loan_type": "bank_loan"})
    assert res.status_code == 401


def test_create_list_get_update_delete_debt(client, auth_headers):
    create_res = client.post(
        "/api/v1/debts",
        headers=auth_headers,
        json={"name": "loan", "loan_type": "bank_loan"},
    )
    assert create_res.status_code == 201
    debt_id = create_res.json()["id"]

    list_res = client.get("/api/v1/debts", headers=auth_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    get_res = client.get(f"/api/v1/debts/{debt_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "loan"

    patch_res = client.patch(
        f"/api/v1/debts/{debt_id}",
        headers=auth_headers,
        json={"name": "renamed"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "renamed"

    del_res = client.delete(f"/api/v1/debts/{debt_id}", headers=auth_headers)
    assert del_res.status_code == 204

    missing = client.get(f"/api/v1/debts/{debt_id}", headers=auth_headers)
    assert missing.status_code == 404


def test_cannot_access_other_users_debt_by_id(client, db_session, auth_headers):
    from server.infrastructure.repositories.user_repository import UserRepository

    repo = UserRepository(db_session)
    repo.create("other@example.com", "other-secret")
    db_session.commit()

    create_res = client.post(
        "/api/v1/debts",
        headers=auth_headers,
        json={"name": "mine", "loan_type": "bank_loan"},
    )
    assert create_res.status_code == 201
    debt_id = create_res.json()["id"]

    login_other = client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "other-secret"},
    )
    assert login_other.status_code == 200
    other_headers = {"Authorization": f"Bearer {login_other.json()['access_token']}"}

    res = client.get(f"/api/v1/debts/{debt_id}", headers=other_headers)
    assert res.status_code == 404
