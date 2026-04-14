from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from server.api.v1.health import router as health_router
from server.api.v1.router import api_router
from server.config.settings import settings

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    openapi_version="3.1.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    description="RPML Web App HTTP API (contract snapshot: shared/contracts/openapi/rpml-web-app.v1.yaml).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"10\.\d+\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+"
        r")(?::(3000|5173))?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["ErrorResponse"] = {
        "type": "object",
        "required": ["detail"],
        "title": "ErrorResponse",
        "properties": {
            "detail": {
                "description": (
                    "Error detail: string from HTTPException or list for validation errors."
                ),
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {}},
                ],
            }
        },
    }
    openapi_schema.setdefault("components", {}).setdefault("responses", {})[
        "ErrorContent"
    ] = {
        "description": "Error body for many 4xx/5xx responses (HTTPException).",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
            }
        },
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
app.include_router(health_router)
app.include_router(api_router)
