"""Contract tests: shared OpenAPI snapshot matches runtime schema."""

from __future__ import annotations

from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_openapi_snapshot_exists() -> None:
    snap = _repo_root() / "shared/contracts/openapi/rpml-web-app.v1.yaml"
    assert snap.is_file()


def test_openapi_snapshot_matches_runtime() -> None:
    from server.main import app

    snap = _repo_root() / "shared/contracts/openapi/rpml-web-app.v1.yaml"
    with open(snap, encoding="utf-8") as f:
        snapshot = yaml.safe_load(f)
    assert app.openapi() == snapshot
