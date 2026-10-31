import subprocess
from pathlib import Path

import pytest

from jackpockets import media
from jackpockets.media import MediaError, MediaReport, probe_media


def test_probe_media_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="does not exist"):
        probe_media(tmp_path / "missing.mp4")


def test_master_audio_limits_peaks_without_reencoding_video(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "documentary.mp4"
    target.write_bytes(b"original video")
    monkeypatch.setattr(media, "require_tool", lambda _: "/usr/bin/ffmpeg")

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mastered video")
        assert command[command.index("-c:v") + 1] == "copy"
        assert "alimiter=limit=0.85:attack=5:release=50:level=false" in command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    monkeypatch.setattr(
        media,
        "probe_media",
        lambda path: MediaReport(
            path=str(path),
            duration_seconds=12,
            width=1920,
            height=1080,
            video_codec="h264",
            audio_codec="aac",
            frame_rate=30,
            size_bytes=14,
        ),
    )

    report = media.master_audio_track(target)
    assert report.audio_codec == "aac"
    assert target.read_bytes() == b"mastered video"
