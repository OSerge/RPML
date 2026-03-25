from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from server.config.settings import Settings


class SettingsWithoutEnvFile(Settings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_dotenv_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def test_example_backend_env_file_exists():
    path = _repo_root() / "infra" / "env" / ".env.backend.example"
    assert path.is_file()


def test_settings_loads_required_local_values(monkeypatch: pytest.MonkeyPatch):
    path = _repo_root() / "infra" / "env" / ".env.backend.example"
    data = _parse_dotenv_lines(path.read_text(encoding="utf-8"))
    assert "DATABASE_URL" in data
    assert "JWT_SECRET_KEY" in data

    for key, value in data.items():
        monkeypatch.setenv(key, value)

    s = Settings()
    assert s.database_url.startswith("postgresql")
    assert s.jwt_secret_key == data["JWT_SECRET_KEY"]
    assert "redis" in s.celery_broker_url
    assert "redis" in s.celery_result_backend


def test_settings_fails_without_jwt_when_not_debug(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        SettingsWithoutEnvFile()
