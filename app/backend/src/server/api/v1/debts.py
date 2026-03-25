from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.domain.models.debt import DebtCreate, DebtRead, DebtUpdate, LoanTypeDirectory
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db
from server.infrastructure.repositories.debt_repository import DebtRepository

router = APIRouter()


@router.get("/loan-types", response_model=LoanTypeDirectory)
def list_loan_types() -> LoanTypeDirectory:
    return LoanTypeDirectory()


@router.get("", response_model=list[DebtRead])
def list_debts(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> list[DebtRead]:
    repo = DebtRepository(db)
    rows = repo.list_for_user(current_user.id)
    return [DebtRead.model_validate(r) for r in rows]


@router.post("", response_model=DebtRead, status_code=status.HTTP_201_CREATED)
def create_debt(
    body: DebtCreate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DebtRead:
    repo = DebtRepository(db)
    row = repo.create(current_user.id, body.model_dump(mode="json"))
    db.commit()
    db.refresh(row)
    return DebtRead.model_validate(row)


@router.get("/{debt_id}", response_model=DebtRead)
def get_debt(
    debt_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DebtRead:
    repo = DebtRepository(db)
    row = repo.get_for_user(debt_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    return DebtRead.model_validate(row)


@router.patch("/{debt_id}", response_model=DebtRead)
def update_debt(
    debt_id: int,
    body: DebtUpdate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DebtRead:
    repo = DebtRepository(db)
    row = repo.get_for_user(debt_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    values = body.model_dump(exclude_unset=True, mode="json")
    if not values:
        return DebtRead.model_validate(row)
    repo.update(row, values)
    db.commit()
    db.refresh(row)
    return DebtRead.model_validate(row)


@router.delete("/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_debt(
    debt_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> None:
    repo = DebtRepository(db)
    row = repo.get_for_user(debt_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    repo.delete(row)
    db.commit()
