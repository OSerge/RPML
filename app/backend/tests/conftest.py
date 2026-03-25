import os

os.environ.setdefault("DEBUG", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.infrastructure.db import session as db_session_module
from server.infrastructure.db.base import Base
from server.infrastructure.db.session import get_db
from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.infrastructure.repositories.user_repository import UserRepository
from server.main import app


@pytest.fixture
def db_engine(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    url = f"sqlite:///{db_file}"
    from server.config.settings import settings

    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr(settings, "celery_task_always_eager", True)
    from server.infrastructure.queue.celery_app import celery_app

    celery_app.conf.task_always_eager = bool(settings.celery_task_always_eager)
    celery_app.conf.task_eager_propagates = True
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_session_module, "engine", engine)
    monkeypatch.setattr(db_session_module, "SessionLocal", SessionLocal)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    from server.infrastructure.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine):
    from server.infrastructure.db.session import SessionLocal

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def demo_user(db_session):
    repo = UserRepository(db_session)
    user = repo.create("demo@example.com", "secret")
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, demo_user):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user.email, "password": "secret"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded_debts(db_session, demo_user, client, auth_headers):
    """Two bank loans with full numeric fields and one scenario profile (RPML-ready)."""
    p1, p2 = 1000.0, 2000.0
    for i, principal in enumerate((p1, p2)):
        db_session.add(
            DebtORM(
                user_id=demo_user.id,
                name=f"loan_{i}",
                loan_type="bank_loan",
                principal=principal,
                fixed_payment=100.0 * (i + 1),
                min_payment_pct=0.1,
                prepay_penalty=0.0,
                interest_rate_monthly=0.01,
                default_rate_monthly=0.05,
                stipulated_amount=50.0,
                release_time=0,
            )
        )
    db_session.add(
        ScenarioProfileORM(
            user_id=demo_user.id,
            code="test_scenario",
            horizon_months=120,
            monthly_income_vector=[5000.0] * 120,
            source_json={
                "principals": [p1, p2],
                "fixedPayment": [100.0, 200.0],
                "minPaymentPct": [0.1, 0.1],
                "prepayPenalty": [0.0, 0.0],
                "stipulatedAmount": [50.0, 50.0],
                "loanTypes": ["bank_loan", "bank_loan"],
                "releaseTimeByLoan": [0, 0],
            },
            baseline_reference={},
        )
    )
    db_session.commit()
