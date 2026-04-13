"""Verify Alembic migrations create dashboard seed schema (tables + debt columns)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


@pytest.fixture
def migrated_engine(tmp_path, monkeypatch):
    db_file = tmp_path / "migration_smoke.db"
    url = f"sqlite:///{db_file.resolve()}"

    from server.config.settings import settings

    monkeypatch.setattr(settings, "database_url", url)

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str((backend_root / "alembic").resolve()))
    command.upgrade(cfg, "head")

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        yield engine
    finally:
        engine.dispose()


def test_new_tables_exist(migrated_engine):
    insp = inspect(migrated_engine)
    names = set(insp.get_table_names())
    assert "scenario_profiles" in names
    assert "optimization_runs" in names


def test_debts_extended_columns_exist(migrated_engine):
    insp = inspect(migrated_engine)
    cols = {c["name"] for c in insp.get_columns("debts")}
    expected = {
        "loan_type",
        "principal",
        "fixed_payment",
        "min_payment_pct",
        "prepay_penalty",
        "interest_rate_monthly",
        "default_rate_monthly",
        "stipulated_amount",
        "release_time",
    }
    assert expected.issubset(cols)
