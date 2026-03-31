from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db
from server.services.demo_seed import DemoSeedValidationError, seed_demo_scenario

router = APIRouter()


@router.post("/seed")
def post_demo_seed(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> dict:
    try:
        payload = seed_demo_scenario(db, current_user.id)
    except DemoSeedValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    db.commit()
    return payload
