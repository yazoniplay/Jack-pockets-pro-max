import subprocess
from pathlib import Path

import pytest

from jackpockets import soundtrack
from jackpockets.media import MediaError, MediaReport


def test_ambient_score_is_synthesized_and_verified(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "generated" / "score.wav"
    monkeypatch.setattr(soundtrack, "require_tool", lambda _: "/usr/bin/ffmpeg")

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"RIFF" + b"x" * 80)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(soundtrack.subprocess, "run", fake_run)
    monkeypatch.setattr(
        soundtrack,
        "probe_media",
        lambda path: MediaReport(
            path=str(path),
            duration_seconds=12,
            width=None,
            height=None,
            video_codec=None,
            audio_codec="pcm_s16le",
            frame_rate=None,
            size_bytes=84,
        ),
    )

    result = soundtrack.generate_ambient_score(output, 12)
    assert result == output.resolve()
    assert output.is_file()


def test_ambient_score_rejects_unsupported_duration(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="between 3 and 1800"):
        soundtrack.generate_ambient_score(tmp_path / "score.wav", 2)
