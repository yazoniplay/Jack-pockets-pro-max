"""FFmpeg/FFprobe inspection and strict rendered-file validation."""

from __future__ import annotations

import json
import os
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


def master_audio_track(path: str | Path, timeout_seconds: int = 300) -> MediaReport:
    """Apply a transparent peak limiter while stream-copying the rendered video."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise MediaError("Rendered video is missing before audio mastering.")
    ffmpeg = require_tool("ffmpeg")
    temporary = target.with_name(f"{target.stem}.audio-master{target.suffix}")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(target),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-map_metadata",
                "0",
                "-c:v",
                "copy",
                "-af",
                "alimiter=limit=0.85:attack=5:release=50:level=false",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        temporary.unlink(missing_ok=True)
        raise MediaError("Final audio mastering exceeded the configured time limit.") from exc
    except subprocess.CalledProcessError as exc:
        temporary.unlink(missing_ok=True)
        detail = (exc.stderr or exc.stdout or "")[-1500:]
        raise MediaError(f"Final audio mastering failed: {detail}") from exc

    if not temporary.is_file() or temporary.stat().st_size <= 0:
        temporary.unlink(missing_ok=True)
        raise MediaError("Final audio mastering produced an empty video.")
    try:
        mastered = probe_media(temporary)
        original = probe_media(target)
    except MediaError:
        temporary.unlink(missing_ok=True)
        raise
    if not mastered.video_codec or not mastered.audio_codec:
        temporary.unlink(missing_ok=True)
        raise MediaError("Mastered video is missing its video or audio stream.")
    if abs(mastered.duration_seconds - original.duration_seconds) > 0.15:
        temporary.unlink(missing_ok=True)
        raise MediaError("Audio mastering changed the documentary runtime unexpectedly.")
    os.replace(temporary, target)
    return probe_media(target)


def validate_render(
    path: str | Path,
    min_duration_seconds: float = 30,
    max_duration_seconds: float = 1800,
    require_audio: bool = True,
    expected_width: int = 1920,
    expected_height: int = 1080,
    expected_duration_seconds: float | None = None,
    duration_tolerance_seconds: float = 1.5,
) -> MediaReport:
    report = probe_media(path)
    failures = []
    if report.duration_seconds < min_duration_seconds:
        failures.append(f"duration {report.duration_seconds:.1f}s is below {min_duration_seconds}s")
    if report.duration_seconds > max_duration_seconds:
        failures.append(f"duration {report.duration_seconds:.1f}s exceeds {max_duration_seconds}s")
    if expected_duration_seconds is not None and abs(report.duration_seconds - expected_duration_seconds) > duration_tolerance_seconds:
        failures.append(
            f"duration {report.duration_seconds:.2f}s differs from the approved timeline "
            f"duration {expected_duration_seconds:.2f}s by more than "
            f"{duration_tolerance_seconds:.2f}s"
        )
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
