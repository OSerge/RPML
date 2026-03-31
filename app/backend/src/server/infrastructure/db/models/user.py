from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.infrastructure.db.base import Base


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    debts: Mapped[list["DebtORM"]] = relationship(
        "DebtORM",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    scenario_profiles: Mapped[list["ScenarioProfileORM"]] = relationship(
        "ScenarioProfileORM",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    optimization_runs: Mapped[list["OptimizationRunORM"]] = relationship(
        "OptimizationRunORM",
        back_populates="user",
        cascade="all, delete-orphan",
    )
