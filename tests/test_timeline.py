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
