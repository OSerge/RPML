def test_swagger_ui_available(client):
    res = client.get("/docs")
    assert res.status_code == 200
    assert "Swagger UI" in res.text
