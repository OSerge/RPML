from sqlalchemy import case, select
from sqlalchemy.orm import Session

from server.infrastructure.db.models.debt import DebtORM

_CANONICAL_LOAN_TYPE_ORDER = case(
    (DebtORM.loan_type == "car_loan", 0),
    (DebtORM.loan_type == "house_loan", 1),
    (DebtORM.loan_type == "credit_card", 2),
    (DebtORM.loan_type == "bank_loan", 3),
    else_=4,
)


class DebtRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: int) -> list[DebtORM]:
        stmt = (
            select(DebtORM)
            .where(DebtORM.user_id == user_id)
            .order_by(_CANONICAL_LOAN_TYPE_ORDER.asc(), DebtORM.id.asc())
        )
        return list(self._session.scalars(stmt))

    def get_for_user(self, debt_id: int, user_id: int) -> DebtORM | None:
        row = self._session.get(DebtORM, debt_id)
        if row is None or row.user_id != user_id:
            return None
        return row

    def create(self, user_id: int, values: dict | str) -> DebtORM:
        if isinstance(values, str):
            values = {"name": values}
        debt = DebtORM(user_id=user_id, **values)
        self._session.add(debt)
        self._session.flush()
        return debt

    def update(self, debt: DebtORM, values: dict) -> DebtORM:
        for key, value in values.items():
            setattr(debt, key, value)
        self._session.flush()
        return debt

    def delete(self, debt: DebtORM) -> None:
        self._session.delete(debt)
