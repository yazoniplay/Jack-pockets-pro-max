from jackpockets.assets import (
    FootageCandidate,
    choose_video_file,
    diversify_storyboard_recommendations,
    evaluate_visual_candidates,
    rank_editorial_candidates,
    rank_footage_candidates,
    semantic_relevance,
)


def test_choose_video_file_prefers_high_resolution_mp4() -> None:
    files = [
        {"file_type": "video/mp4", "width": 640, "height": 360, "link": "https://videos.pexels.com/low.mp4"},
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://videos.pexels.com/high.mp4"},
        {"file_type": "video/webm", "width": 3840, "height": 2160, "link": "https://videos.pexels.com/high.webm"},
    ]
    selected = choose_video_file(files)
    assert selected is not None
    assert selected["width"] == 1920


def test_choose_video_file_returns_none_without_mp4() -> None:
    assert choose_video_file([{"file_type": "video/webm", "link": "https://example.com/a.webm"}]) is None


def test_download_rejects_non_pexels_host(tmp_path) -> None:
    import asyncio

    import pytest

    from jackpockets.assets import AssetError, FootageCandidate, download_pexels_video

    candidate = FootageCandidate(
        provider="pexels",
        provider_id="123",
        title="Fake clip",
        creator="Unknown",
        page_url="https://www.pexels.com/video/123/",
        download_url="https://example.com/clip.mp4",
        width=1920,
        height=1080,
        duration_seconds=10,
        license_name="Pexels License",
        license_url="https://www.pexels.com/license/",
    )
    with pytest.raises(AssetError, match="non-Pexels"):
        asyncio.run(download_pexels_video(candidate, tmp_path / "clip.mp4"))


def test_footage_ranking_prefers_full_hd_landscape_clip_that_covers_beat() -> None:
    candidates = [
        FootageCandidate(
            provider="pexels", provider_id="1", title="Low resolution",
            creator="Creator", page_url="https://www.pexels.com/video/1/",
            download_url="https://videos.pexels.com/1.mp4", width=640, height=360,
            duration_seconds=4, license_name="Pexels License",
            license_url="https://www.pexels.com/license/",
        ),
        FootageCandidate(
            provider="pexels", provider_id="2", title="Full HD",
            creator="Creator", page_url="https://www.pexels.com/video/2/",
            download_url="https://videos.pexels.com/2.mp4", width=1920, height=1080,
            duration_seconds=12, license_name="Pexels License",
            license_url="https://www.pexels.com/license/",
        ),
    ]
    ranked = rank_footage_candidates(candidates, target_duration_seconds=10)
    assert ranked[0]["provider_id"] == "2"
    assert ranked[0]["quality_score"] > ranked[1]["quality_score"]
    assert "covers beat" in ranked[0]["quality_notes"][-1]


def test_footage_ranking_is_bounded_and_reports_short_clips() -> None:
    candidate = FootageCandidate(
        provider="pexels", provider_id="3", title="Short clip",
        creator="Creator", page_url="https://www.pexels.com/video/3/",
        download_url="https://videos.pexels.com/3.mp4", width=1920, height=1080,
        duration_seconds=3, license_name="Pexels License",
        license_url="https://www.pexels.com/license/",
    )
    ranked = rank_footage_candidates([candidate], target_duration_seconds=12)
    assert 0 <= ranked[0]["quality_score"] <= 100
    assert ranked[0]["quality_notes"][-1] == "Duration: shorter than beat"


def test_semantic_relevance_uses_provider_tags_and_explains_matches() -> None:
    candidate = FootageCandidate(
        provider="pexels", provider_id="44", title="Pexels footage 44",
        creator="Creator", page_url="https://www.pexels.com/video/ancient-rome-44/",
        download_url="https://videos.pexels.com/44.mp4", width=1920, height=1080,
        duration_seconds=18, license_name="Pexels License",
        license_url="https://www.pexels.com/license/", tags=("ancient Rome", "colosseum", "history"),
    )
    result = semantic_relevance(candidate, "Rome expanded across the Mediterranean", "Ancient Roman city", "Roman architecture")
    assert result["score"] > 0
    assert result["evidence"] == "metadata"
    assert any("rome" in note.lower() for note in result["notes"])


def test_editorial_ranking_keeps_visual_and_technical_scores_separate() -> None:
    relevant = FootageCandidate(
        provider="pexels", provider_id="51", title="Roman forum", creator="Creator",
        page_url="https://www.pexels.com/video/roman-forum-51/",
        download_url="https://videos.pexels.com/51.mp4", width=1920, height=1080,
        duration_seconds=12, license_name="Pexels License",
        license_url="https://www.pexels.com/license/", tags=("rome", "forum", "ancient"),
    )
    generic = FootageCandidate(
        provider="pexels", provider_id="52", title="Ocean waves", creator="Creator",
        page_url="https://www.pexels.com/video/ocean-waves-52/",
        download_url="https://videos.pexels.com/52.mp4", width=1920, height=1080,
        duration_seconds=12, license_name="Pexels License",
        license_url="https://www.pexels.com/license/", tags=("ocean", "water"),
    )
    ranked = rank_editorial_candidates([generic, relevant], "Rome's public forums shaped civic life", "Ancient Roman forum", "Roman forum")
    assert ranked[0]["provider_id"] == "51"
    assert ranked[0]["editorial_score"] >= ranked[1]["editorial_score"]
    assert "quality_score" in ranked[0] and "semantic_score" in ranked[0]


def test_cross_beat_diversity_avoids_reusing_the_same_top_clip() -> None:
    recommendations = [
        {"beat_id": "a", "results": [{"provider_id": "same", "editorial_score": 95}, {"provider_id": "a2", "editorial_score": 70}]},
        {"beat_id": "b", "results": [{"provider_id": "same", "editorial_score": 90}, {"provider_id": "b2", "editorial_score": 80}]},
    ]
    result = diversify_storyboard_recommendations(recommendations)
    selected = {item["recommended_provider_id"] for item in result}
    assert selected == {"same", "b2"}
    assert all(any(candidate.get("recommended_for_beat") for candidate in item["results"]) for item in result)

def test_visual_evaluation_uses_preview_frame_and_model_score(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import httpx

    class FakeResponse:
        def __init__(self):
            self.content = b"fake-image-bytes"
            self.headers = {"content-type": "image/jpeg"}
            self.url = "https://images.pexels.com/frame.jpg"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, url): return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())

    class FakeVisionProvider:
        async def generate_with_images(self, system, prompt, images):
            assert len(images) == 1
            assert images[0][0] == b"fake-image-bytes"
            return SimpleNamespace(text='{"scores":[{"provider_id":"77","score":94,"reason":"The frame clearly shows the Roman forum"}]}')

    candidates = [{
        "provider_id": "77", "thumbnail_url": "https://images.pexels.com/frame.jpg",
        "semantic_score": 50, "quality_score": 80, "editorial_score": 59,
    }]
    result = asyncio.run(evaluate_visual_candidates(candidates, "Roman civic life", "Roman forum", "ancient Rome", FakeVisionProvider()))
    assert result[0]["visual_score"] == 94
    assert result[0]["visual_evidence"] == "gemini_preview_frame"
    assert result[0]["editorial_score"] > 59