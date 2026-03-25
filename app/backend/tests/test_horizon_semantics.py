from sqlalchemy import select

from server.infrastructure.db.models.optimization_run import OptimizationRunORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM


def test_run_horizon_overrides_profile_default_without_mutating_profile(
    client,
    auth_headers,
    seeded_debts,
    db_session,
):
    profile_before = db_session.scalars(
        select(ScenarioProfileORM).where(ScenarioProfileORM.code == "test_scenario")
    ).first()
    assert profile_before is not None
    assert profile_before.horizon_months == 120

    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 18},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["horizon_months"] == 18

    db_session.expire_all()
    profile_after = db_session.scalars(
        select(ScenarioProfileORM).where(ScenarioProfileORM.id == profile_before.id)
    ).first()
    assert profile_after is not None
    assert profile_after.horizon_months == 120

    last_run = db_session.scalars(
        select(OptimizationRunORM).order_by(OptimizationRunORM.id.desc())
    ).first()
    assert last_run is not None
    assert last_run.result_json is not None
    assert last_run.result_json["horizon_months"] == 18
