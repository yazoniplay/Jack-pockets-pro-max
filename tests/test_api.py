from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jackpockets.api import app
from jackpockets.config import get_settings
from jackpockets.storage import update_job


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["configured_providers"] == []


def test_create_and_retrieve_documentary_job(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        json={"brief": {"topic": "How the Panama Canal changed global trade", "target_minutes": 12}},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["brief"]["topic"] == "How the Panama Canal changed global trade"
    assert payload["events"][0]["type"] == "job.created"
    detail = client.get(f"/api/jobs/{payload['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == payload["id"]


def test_create_job_rejects_invalid_topic(client: TestClient) -> None:
    response = client.post("/api/jobs", json={"brief": {"topic": "x"}})
    assert response.status_code == 422


def test_missing_job_returns_404(client: TestClient) -> None:
    response = client.get("/api/jobs/not-a-real-id")
    assert response.status_code == 404


def test_provider_status_does_not_claim_collaboration_without_keys(client: TestClient) -> None:
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert response.json()["providers"] == []
    assert response.json()["collaboration_ready"] is False


def test_run_without_provider_fails_honestly(client: TestClient) -> None:
    created = client.post(
        "/api/jobs", json={"brief": {"topic": "The history of the printing press"}}
    ).json()
    response = client.post(f"/api/jobs/{created['id']}/run")
    assert response.status_code == 202
    final_state = client.get(f"/api/jobs/{created['id']}").json()
    assert final_state["status"] == "failed"
    assert "No AI providers are configured" in final_state["error"]


def test_footage_search_requires_pexels_key(client: TestClient) -> None:
    response = client.get("/api/assets/search?query=ancient%20rome")
    assert response.status_code == 503
    assert "PEXELS_API_KEY" in response.json()["detail"]


def test_footage_selection_rejects_unknown_storyboard_beat(client: TestClient) -> None:
    created = client.post(
        "/api/jobs", json={"brief": {"topic": "The history of the Silk Road"}}
    ).json()
    update_job(
        created["id"],
        "needs_review",
        "test.storyboard_ready",
        result={"storyboard": {"beats": [{"id": "beat-01"}]}},
    )
    response = client.post(
        f"/api/jobs/{created['id']}/assets",
        json={
            "provider_id": "12345",
            "beat_id": "not-a-real-beat",
            "title": "Test clip",
            "creator": "Test creator",
            "page_url": "https://www.pexels.com/video/test/",
            "media_uri": "https://videos.pexels.com/video-files/test.mp4",
            "width": 1920,
            "height": 1080,
            "duration_seconds": 12,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown storyboard beat id."
