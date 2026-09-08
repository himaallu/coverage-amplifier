from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_healthz_returns_200_and_payload() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "unknown"}
