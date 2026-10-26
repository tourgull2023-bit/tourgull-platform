"""TG-ENG-001.4: readiness behavior under dependency failures.

All dependency calls are mocked: these tests do not require live databases.
The Docker integration job separately verifies real service connectivity.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_independent_of_dependencies():
    with patch("app.main.connect", side_effect=ConnectionError("database offline")):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "tourgull-api"}


def test_ready_when_postgres_and_redis_respond(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    cursor = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
    with patch("app.main.connect", return_value=connection) as connect_mock, patch(
        "app.main.Redis.from_url"
    ) as redis_mock:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    cursor.execute.assert_called_once_with("SELECT 1")
    connect_mock.assert_called_once_with("postgresql://example", connect_timeout=3)
    redis_mock.return_value.ping.assert_called_once()


@pytest.mark.parametrize("missing", ["DATABASE_URL", "REDIS_URL"])
def test_ready_returns_503_when_configuration_missing(monkeypatch, missing):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.delenv(missing)
    with patch("app.main.connect") as connect_mock, patch("app.main.Redis.from_url"):
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dependencies unavailable"}


def test_ready_returns_503_when_postgres_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    with patch("app.main.connect", side_effect=ConnectionError("sensitive database detail")):
        response = client.get("/ready")
    assert response.status_code == 503
    assert "sensitive database detail" not in response.text


def test_ready_returns_503_when_redis_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    connection = MagicMock()
    with patch("app.main.connect", return_value=connection), patch(
        "app.main.Redis.from_url", side_effect=ConnectionError("sensitive redis detail")
    ):
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dependencies unavailable"}
    assert "sensitive redis detail" not in response.text
