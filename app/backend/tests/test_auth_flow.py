def test_login_returns_access_token(client, demo_user):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user.email, "password": "secret"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_rejects_wrong_password(client, demo_user):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user.email, "password": "wrong"},
    )
    assert res.status_code == 401


def test_login_unknown_email_returns_401(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "any-password"},
    )
    assert res.status_code == 401


def test_login_preflight_options_is_allowed(client):
    res = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
