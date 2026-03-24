"""Smoke tests for repository directory layout."""

from pathlib import Path


def test_monorepo_dirs_exist():
    root = Path(__file__).resolve().parent.parent
    assert (root / "core").is_dir()
    assert (root / "app").is_dir()
    assert (root / "shared" / "contracts" / "openapi").is_dir()
    assert (root / "infra" / "docker").is_dir()
    assert (root / "infra" / "env").is_dir()
    assert (root / "infra" / "scripts").is_dir()
