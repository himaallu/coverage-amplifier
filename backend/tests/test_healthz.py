from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


def test_healthz_healthy_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set a valid in-memory or working connection string
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_healthz_down_db(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Set an invalid/unreachable connection string that fails instantly
    monkeypatch.setenv(
        "DATABASE_URL",
        "sqlite:////dev/null/nonexistent/invalid.db",
    )
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "down"}
