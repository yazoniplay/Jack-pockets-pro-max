import pytest
from pydantic import ValidationError

from jackpockets.timeline import TimelineManifest


def test_timeline_exports_remotion_props() -> None:
    manifest = TimelineManifest(
        title="A documentary",
        scenes=[
            {
                "id": "intro",
                "kind": "title",
                "duration_frames": 90,
                "title": "The beginning",
            }
        ],
        captions=[{"start_frame": 0, "end_frame": 45, "text": "Opening line"}],
    )
    props = manifest.to_remotion_props()
    assert props["scenes"][0]["durationInFrames"] == 90
    assert props["captions"][0]["text"] == "Opening line"


def test_footage_requires_license_provenance() -> None:
    with pytest.raises(ValidationError):
        TimelineManifest(
            title="A documentary",
            scenes=[
                {
                    "id": "shot",
                    "kind": "footage",
                    "duration_frames": 90,
                    "title": "Unlicensed footage",
                }
            ],
        )


def test_adjacent_repeated_footage_is_rejected() -> None:
    asset = {
        "source_url": "https://example.com/clip.mp4",
        "title": "Sample clip",
        "license_name": "CC BY 4.0",
        "local_file": "assets/sample.mp4",
    }
    with pytest.raises(ValidationError, match="Adjacent scenes"):
        TimelineManifest(
            title="A documentary",
            scenes=[
                {"id": "one", "kind": "footage", "duration_frames": 90, "title": "A", "asset": asset},
                {"id": "two", "kind": "footage", "duration_frames": 90, "title": "B", "asset": asset},
            ],
        )


def test_caption_cannot_extend_beyond_timeline() -> None:
    with pytest.raises(ValidationError, match="beyond"):
        TimelineManifest(
            title="A documentary",
            scenes=[{"id": "intro", "kind": "title", "duration_frames": 90, "title": "Intro"}],
            captions=[{"start_frame": 0, "end_frame": 100, "text": "Too long"}],
        )


@pytest.mark.parametrize("unsafe_path", [
    "../secret.txt",
    "assets/../../secret.txt",
    "/etc/passwd",
    r"assets\\..\\secret.txt",
])
def test_timeline_rejects_unsafe_asset_paths(unsafe_path: str) -> None:
    with pytest.raises(ValidationError):
        TimelineManifest(
            title="Unsafe timeline",
            scenes=[
                {
                    "id": "shot",
                    "kind": "footage",
                    "duration_frames": 90,
                    "title": "Unsafe",
                    "asset": {
                        "source_url": "https://example.com/clip.mp4",
                        "local_file": unsafe_path,
                        "title": "Clip",
                        "license_name": "Example license",
                    },
                }
            ],
        )


def test_timeline_rejects_unknown_scene_kind() -> None:
    with pytest.raises(ValidationError):
        TimelineManifest(
            title="Unknown scene",
            scenes=[
                {
                    "id": "shot",
                    "kind": "explosion",
                    "duration_frames": 90,
                    "title": "Unknown",
                }
            ],
        )


def test_footage_source_credit_is_passed_to_renderer() -> None:
    manifest = TimelineManifest(
        title="A documentary",
        scenes=[
            {
                "id": "shot",
                "kind": "footage",
                "duration_frames": 90,
                "title": "Aerial city",
                "asset": {
                    "source_url": "https://example.com/clip.mp4",
                    "local_file": "assets/clip.mp4",
                    "title": "Aerial city",
                    "creator": "Example Creator",
                    "license_name": "CC BY 4.0",
                },
            }
        ],
    )
    scene = manifest.to_remotion_props()["scenes"][0]
    assert scene["sourceCredit"] == "Footage: Example Creator · CC BY 4.0"


def test_original_score_is_enabled_by_default_and_deferred_to_render_assembly() -> None:
    manifest = TimelineManifest(
        title="A documentary",
        scenes=[{"id": "intro", "kind": "title", "duration_frames": 90, "title": "Intro"}],
    )
    assert manifest.music_enabled is True
    assert manifest.to_remotion_props()["musicSrc"] is None


def test_original_score_can_be_disabled() -> None:
    manifest = TimelineManifest(
        title="A silent documentary",
        music_enabled=False,
        scenes=[{"id": "intro", "kind": "title", "duration_frames": 90, "title": "Intro"}],
    )
    assert manifest.to_remotion_props()["musicSrc"] is None
