from fastapi.testclient import TestClient

from jackpockets.api import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_job_accepts_valid_brief() -> None:
    response = client.post(
        "/api/jobs",
        json={
            "topic": "How the Panama Canal changed global trade",
            "target_minutes": 12,
            "language": "en",
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["brief"]["topic"] == "How the Panama Canal changed global trade"
    assert "Research has not started" in payload["message"]


def test_create_job_rejects_too_short_topic() -> None:
    response = client.post("/api/jobs", json={"topic": "x"})
    assert response.status_code == 422
