"""AI explanation chat endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.v1.deps import require_current_user
from app.models.user import User
from app.services.explanation import ExplanationService

router = APIRouter()


class ExplainRequest(BaseModel):
    question: str
    plan_context: str | None = None


@router.post("")
async def explain(
    data: ExplainRequest,
    current_user: User = Depends(require_current_user),
):
    service = ExplanationService()

    async def generate():
        async for chunk in service.explain_stream(data.question, data.plan_context):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )
