from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.infrastructure.db.base import Base


class ScenarioProfileORM(Base):
    __tablename__ = "scenario_profiles"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_scenario_profiles_user_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_income_vector: Mapped[list] = mapped_column(JSON, nullable=False)
    source_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    baseline_reference: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    user: Mapped["UserORM"] = relationship("UserORM", back_populates="scenario_profiles")
    optimization_runs: Mapped[list["OptimizationRunORM"]] = relationship(
        "OptimizationRunORM",
        back_populates="scenario_profile",
        cascade="all, delete-orphan",
    )
