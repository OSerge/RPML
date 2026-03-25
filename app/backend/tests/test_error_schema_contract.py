"""Contract tests: unified error body shape in OpenAPI (detail)."""


def test_openapi_contains_standard_error_schema() -> None:
    from server.main import app

    schema = app.openapi()
    assert "ErrorResponse" in schema["components"]["schemas"]
    er = schema["components"]["schemas"]["ErrorResponse"]
    assert er.get("required") == ["detail"]
    assert "detail" in er.get("properties", {})
    responses = schema["components"].get("responses", {})
    assert "ErrorContent" in responses
    assert responses["ErrorContent"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
