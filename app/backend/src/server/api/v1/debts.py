from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.domain.models.debt import DebtCreate, DebtRead, DebtUpdate, LoanTypeDirectory
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db
from server.infrastructure.repositories.debt_repository import DebtRepository

router = APIRouter()


@router.get(
    "/loan-types",
    response_model=LoanTypeDirectory,
    summary="Справочник типов кредитов",
    description="Возвращает список допустимых значений `loan_type` для операций создания/обновления долгов.",
)
def list_loan_types() -> LoanTypeDirectory:
    return LoanTypeDirectory()


@router.get(
    "",
    response_model=list[DebtRead],
    summary="Список долгов пользователя",
    description="Возвращает все долги текущего аутентифицированного пользователя.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
    },
)
def list_debts(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> list[DebtRead]:
    repo = DebtRepository(db)
    rows = repo.list_for_user(current_user.id)
    return [DebtRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=DebtRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать долг",
    description=(
        "Создает новый долг для текущего пользователя. "
        "Для последующего расчета оптимизации должны быть заполнены все числовые параметры долга."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        422: {"description": "Ошибка валидации тела запроса."},
    },
)
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


@router.get(
    "/{debt_id}",
    response_model=DebtRead,
    summary="Получить долг по ID",
    description="Возвращает один долг текущего пользователя по идентификатору.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"description": "Долг не найден."},
    },
)
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


@router.patch(
    "/{debt_id}",
    response_model=DebtRead,
    summary="Обновить долг",
    description=(
        "Частично обновляет поля долга по ID. "
        "Передаются только поля, которые нужно изменить."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"description": "Долг не найден."},
        422: {"description": "Ошибка валидации тела запроса."},
    },
)
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


@router.delete(
    "/{debt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить долг",
    description="Удаляет долг текущего пользователя по ID.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"description": "Долг не найден."},
    },
)
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
