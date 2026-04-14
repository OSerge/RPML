"""Tests for idempotent demo scenario seeding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.services.demo_seed import (
    DemoSeedValidationError,
    debt_name_prefix_for_scenario,
    validate_seed_document,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_JSON = REPO_ROOT / "core" / "rpml" / "result_samples" / "Deudas_4_0_0_2_2_120_fijo_fijo_0.json"
DEMO_SCENARIO_CODE = "Deudas_4_0_0_2_2_120_fijo_fijo_0"
EXPECTED_INTEREST_RATES = [
    0.007004809170188,
    0.011494390008270,
    0.019510771638952,
    0.017538935859939,
]
EXPECTED_DEFAULT_RATES = [
    0.027676437839094,
    0.017890761655084,
    0.028471667477149,
    0.049981955115985,
]
EXPECTED_LOAN_TYPES = [
    "credit_card",
    "credit_card",
    "bank_loan",
    "bank_loan",
]


def test_demo_seed_is_idempotent(client, auth_headers, db_session, demo_user):
    first = client.post("/api/v1/demo/seed", headers=auth_headers)
    second = client.post("/api/v1/demo/seed", headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200

    n_debts = db_session.scalar(
        select(func.count()).select_from(DebtORM).where(DebtORM.user_id == demo_user.id)
    )
    assert n_debts == 4

    n_profiles = db_session.scalar(
        select(func.count())
        .select_from(ScenarioProfileORM)
        .where(ScenarioProfileORM.user_id == demo_user.id)
    )
    assert n_profiles == 1


def test_demo_instances_catalog_lists_bundled_scenarios(client, auth_headers):
    res = client.get("/api/v1/demo/instances", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    codes = [item["code"] for item in body]
    assert DEMO_SCENARIO_CODE in codes
    assert "Deudas_4_0_0_0_4_120_fijo_fijo_3" in codes
    current = next(item for item in body if item["code"] == DEMO_SCENARIO_CODE)
    assert current["horizon_months"] == 120
    assert current["loans_count"] == 4
    assert "milp" in current["available_baselines"]


def test_demo_seed_accepts_specific_scenario_code(client, auth_headers, db_session, demo_user):
    response = client.post(
        "/api/v1/demo/seed",
        headers=auth_headers,
        json={"scenario_code": "Deudas_4_0_0_0_4_120_fijo_fijo_3"},
    )
    assert response.status_code == 200
    assert response.json()["scenario_code"] == "Deudas_4_0_0_0_4_120_fijo_fijo_3"

    profile = db_session.scalars(
        select(ScenarioProfileORM).where(ScenarioProfileORM.user_id == demo_user.id)
    ).first()
    assert profile is not None
    assert profile.code == "Deudas_4_0_0_0_4_120_fijo_fijo_3"


def test_demo_seed_404_on_unknown_scenario_code(client, auth_headers):
    response = client.post(
        "/api/v1/demo/seed",
        headers=auth_headers,
        json={"scenario_code": "missing_demo_code"},
    )
    assert response.status_code == 404


def test_demo_seed_scenario_profile_source_and_baseline(client, auth_headers, db_session, demo_user):
    r = client.post("/api/v1/demo/seed", headers=auth_headers)
    assert r.status_code == 200

    profile = db_session.scalars(
        select(ScenarioProfileORM).where(ScenarioProfileORM.user_id == demo_user.id)
    ).first()
    assert profile is not None
    assert profile.code == DEMO_SCENARIO_CODE
    assert profile.horizon_months == 120
    assert isinstance(profile.monthly_income_vector, list)
    assert len(profile.monthly_income_vector) == 120

    assert profile.source_json is not None
    src = profile.source_json
    assert isinstance(src, dict)
    for key in (
        "principals",
        "fixedPayment",
        "minPaymentPct",
        "prepayPenalty",
        "stipulatedAmount",
        "monthlyIncome",
        "horizonMonths",
        "loanTypes",
        "releaseTimeByLoan",
        "seedMetadata",
    ):
        assert key in src

    meta = src["seedMetadata"]
    assert meta["strategy"] == "source_dat_rates"
    assert meta["ratesApplied"]["interestRateMonthlyByLoan"] == EXPECTED_INTEREST_RATES
    assert meta["ratesApplied"]["defaultRateMonthlyByLoan"] == EXPECTED_DEFAULT_RATES
    assert "rates" in meta["assumptions"]

    assert profile.baseline_reference is not None
    br = profile.baseline_reference
    assert isinstance(br, dict)
    assert "milp" in br and "avalanche" in br and "snowball" in br


def test_demo_seed_debt_required_fields(client, auth_headers, db_session, demo_user):
    client.post("/api/v1/demo/seed", headers=auth_headers)
    debts = db_session.scalars(select(DebtORM).where(DebtORM.user_id == demo_user.id)).all()
    assert len(debts) == 4
    for d in debts:
        idx = int(d.name.split("_loan_")[-1])
        assert d.loan_type == EXPECTED_LOAN_TYPES[idx]
        assert d.principal is not None
        assert d.fixed_payment is not None
        assert d.min_payment_pct is not None
        assert d.prepay_penalty is not None
        assert d.interest_rate_monthly == EXPECTED_INTEREST_RATES[idx]
        assert d.default_rate_monthly == EXPECTED_DEFAULT_RATES[idx]
        assert d.stipulated_amount is not None
        assert d.release_time is not None


def test_sample_json_fixture_exists():
    assert SAMPLE_JSON.is_file()


def test_validate_accepts_official_sample():
    raw = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    instance, summary = validate_seed_document(raw)
    assert instance["name"] == DEMO_SCENARIO_CODE
    assert "milp" in summary


def test_validate_rejects_horizon_income_mismatch():
    raw = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    raw["instance"]["monthlyIncome"] = raw["instance"]["monthlyIncome"][:10]
    with pytest.raises(DemoSeedValidationError, match="monthlyIncome"):
        validate_seed_document(raw)


def test_validate_rejects_loan_vector_length_mismatch():
    raw = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    raw["instance"]["principals"] = raw["instance"]["principals"][:2]
    with pytest.raises(DemoSeedValidationError, match="principals"):
        validate_seed_document(raw)


def test_validate_rejects_missing_instance_key():
    raw = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    del raw["instance"]["loanTypes"]
    with pytest.raises(DemoSeedValidationError, match="loanTypes"):
        validate_seed_document(raw)


def test_post_seed_422_on_invalid_export(client, auth_headers, tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"instance": {"name": "x"}, "summary": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("server.services.demo_seed.default_seed_json_path", lambda: bad)
    r = client.post("/api/v1/demo/seed", headers=auth_headers)
    assert r.status_code == 422


def test_reseed_does_not_delete_debt_with_unrelated_name(client, auth_headers, db_session, demo_user):
    from server.infrastructure.repositories.debt_repository import DebtRepository

    repo = DebtRepository(db_session)
    extra = repo.create(demo_user.id, "manual_other_debt")
    db_session.commit()
    db_session.refresh(extra)

    client.post("/api/v1/demo/seed", headers=auth_headers)
    names = {r.name for r in db_session.scalars(select(DebtORM).where(DebtORM.user_id == demo_user.id)).all()}
    assert "manual_other_debt" in names
    prefix = debt_name_prefix_for_scenario(DEMO_SCENARIO_CODE)
    seeded = {n for n in names if n.startswith(prefix)}
    assert len(seeded) == 4


def test_demo_seed_replaces_previous_demo_scenario_rows(client, auth_headers, db_session, demo_user):
    old_code = "Deudas_4_0_0_0_4_120_fijo_fijo_3"
    old_prefix = debt_name_prefix_for_scenario(old_code)
    db_session.add(
        ScenarioProfileORM(
            user_id=demo_user.id,
            code=old_code,
            horizon_months=120,
            monthly_income_vector=[1.0] * 120,
            source_json={"principals": [1, 2, 3, 4]},
            baseline_reference={"milp": {}},
        )
    )
    for idx in range(4):
        db_session.add(DebtORM(user_id=demo_user.id, name=f"{old_prefix}{idx}"))
    db_session.commit()

    response = client.post("/api/v1/demo/seed", headers=auth_headers)
    assert response.status_code == 200

    profile_codes = {
        row.code
        for row in db_session.scalars(
            select(ScenarioProfileORM).where(ScenarioProfileORM.user_id == demo_user.id)
        ).all()
    }
    assert profile_codes == {DEMO_SCENARIO_CODE}

    names = {
        row.name
        for row in db_session.scalars(select(DebtORM).where(DebtORM.user_id == demo_user.id)).all()
    }
    assert all(not name.startswith(old_prefix) for name in names)


def test_demo_seed_replaces_legacy_unprefixed_demo_debts(client, auth_headers, db_session, demo_user):
    for idx in range(4):
        db_session.add(DebtORM(user_id=demo_user.id, name=f"loan_{idx}"))
    db_session.commit()

    response = client.post("/api/v1/demo/seed", headers=auth_headers)
    assert response.status_code == 200

    names = {
        row.name
        for row in db_session.scalars(select(DebtORM).where(DebtORM.user_id == demo_user.id)).all()
    }
    assert all(name not in names for name in {"loan_0", "loan_1", "loan_2", "loan_3"})


def test_demo_run_top_savings_returns_sorted_rows(client, auth_headers, tmp_path, monkeypatch):
    from server.api.v1 import demo as demo_api

    run_id = "20260406-211020_base_std_n4_tl300_m110_b0327b96"
    checkpoint_dir = tmp_path / "core" / "rpml" / "tmp" / "runs" / run_id / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "experiment_results_checkpoint.jsonl"
    checkpoint_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "instance_name": "inst_a",
                        "optimal_cost": 100.0,
                        "avalanche_cost": 200.0,
                        "avalanche_savings": 50.0,
                        "optimal_status": "OPTIMAL",
                    }
                ),
                json.dumps(
                    {
                        "instance_name": "inst_b",
                        "optimal_cost": 100.0,
                        "avalanche_cost": 125.0,
                        "avalanche_savings": 20.0,
                        "optimal_status": "OPTIMAL",
                    }
                ),
                json.dumps(
                    {
                        "instance_name": "inst_c",
                        "optimal_cost": 100.0,
                        "avalanche_cost": 110.0,
                        "avalanche_savings": 9.0,
                        "optimal_status": "FEASIBLE",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(demo_api, "_repo_root", lambda: tmp_path)

    response = client.get(
        f"/api/v1/demo/runs/{run_id}/top-savings?metric=avalanche&limit=2",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["metric"] == "avalanche"
    assert body["total_instances"] == 3
    assert [row["instance_name"] for row in body["items"]] == ["inst_a", "inst_b"]


def test_demo_run_top_savings_404_when_run_missing(client, auth_headers):
    response = client.get(
        "/api/v1/demo/runs/missing-run/top-savings",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_demo_run_top_savings_rejects_invalid_run_id(client, auth_headers):
    response = client.get(
        "/api/v1/demo/runs/bad$run/top-savings",
        headers=auth_headers,
    )
    assert response.status_code == 422
