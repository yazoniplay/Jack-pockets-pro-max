"""FFmpeg/FFprobe inspection and strict rendered-file validation."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    """Media tooling is missing or an output file is invalid."""


@dataclass(frozen=True)
class MediaReport:
    path: str
    duration_seconds: float
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    frame_rate: float | None
    size_bytes: int


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise MediaError(f"Required media tool '{name}' is not installed or not on PATH.")
    return executable


def probe_media(path: str | Path, timeout_seconds: int = 30) -> MediaReport:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise MediaError(f"Media file does not exist: {target}")
    ffprobe = require_tool("ffprobe")
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_streams", "-show_format",
                "-of", "json", str(target),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
        payload = json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("FFprobe timed out while inspecting the media file.") from exc
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise MediaError("FFprobe could not parse the media file.") from exc

    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = float(payload.get("format", {}).get("duration") or 0)
    rate = None
    if video and video.get("avg_frame_rate") not in (None, "0/0"):
        numerator, denominator = video["avg_frame_rate"].split("/")
        if float(denominator):
            rate = float(numerator) / float(denominator)
    return MediaReport(
        path=str(target),
        duration_seconds=duration,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        video_codec=video.get("codec_name") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
        frame_rate=rate,
        size_bytes=target.stat().st_size,
    )


def validate_render(
    path: str | Path,
    min_duration_seconds: float = 30,
    max_duration_seconds: float = 1800,
    require_audio: bool = True,
    expected_width: int = 1920,
    expected_height: int = 1080,
) -> MediaReport:
    report = probe_media(path)
    failures = []
    if report.duration_seconds < min_duration_seconds:
        failures.append(f"duration {report.duration_seconds:.1f}s is below {min_duration_seconds}s")
    if report.duration_seconds > max_duration_seconds:
        failures.append(f"duration {report.duration_seconds:.1f}s exceeds {max_duration_seconds}s")
    if report.width != expected_width or report.height != expected_height:
        failures.append(
            f"resolution is {report.width}x{report.height}; expected {expected_width}x{expected_height}"
        )
    if not report.video_codec:
        failures.append("video stream is missing")
    if require_audio and not report.audio_codec:
        failures.append("audio stream is missing")
    if report.size_bytes <= 0:
        failures.append("output file is empty")
    if failures:
        raise MediaError("Render validation failed: " + "; ".join(failures))
    return report
