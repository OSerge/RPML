from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Проверка доступности API",
    description="Технический эндпоинт для liveness-проверок и мониторинга.",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}
