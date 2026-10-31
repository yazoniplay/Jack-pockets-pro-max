"""Generate an original, royalty-free ambient score with FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .media import MediaError, probe_media, require_tool


def generate_ambient_score(
    output_path: str | Path,
    duration_seconds: float,
    timeout_seconds: int = 180,
) -> Path:
    """Synthesize a restrained evolving ambient bed; no external audio is downloaded."""
    if not 3 <= duration_seconds <= 1800:
        raise MediaError("Ambient score duration must be between 3 and 1800 seconds.")

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = require_tool("ffmpeg")
    duration = f"{duration_seconds:.3f}"

    # A slow A-minor-inspired pad with gentle modulation and stereo phase variation.
    left = (
        "0.16*sin(2*PI*110*t+0.12*sin(2*PI*0.035*t))"
        "+0.09*sin(2*PI*164.81*t+0.08*sin(2*PI*0.025*t))"
        "+0.05*sin(2*PI*220*t+0.06*sin(2*PI*0.021*t))"
        "+0.025*sin(2*PI*261.63*t+0.05*sin(2*PI*0.017*t))"
    )
    right = (
        "0.16*sin(2*PI*110*t+0.12*sin(2*PI*0.035*t+0.15))"
        "+0.09*sin(2*PI*164.81*t+0.08*sin(2*PI*0.025*t+0.1))"
        "+0.05*sin(2*PI*220*t+0.06*sin(2*PI*0.021*t+0.2))"
        "+0.025*sin(2*PI*261.63*t+0.05*sin(2*PI*0.017*t+0.12))"
    )
    source = f"aevalsrc={left}|{right}:s=48000:d={duration}"
    fade_in = min(4.0, duration_seconds / 3)
    fade_out = min(5.0, duration_seconds / 3)
    fade_out_start = max(0.0, duration_seconds - fade_out)
    audio_filter = (
        f"lowpass=f=1200,"
        f"afade=t=in:st=0:d={fade_in:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f},"
        "alimiter=limit=0.85"
    )
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        source,
        "-af",
        audio_filter,
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Original ambient score generation timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "")[-1200:]
        raise MediaError(f"Ambient score generation failed: {detail}") from exc

    if not target.is_file() or target.stat().st_size <= 44:
        raise MediaError("Ambient score generation produced an empty audio file.")
    report = probe_media(target)
    if not report.audio_codec or abs(report.duration_seconds - duration_seconds) > 0.15:
        raise MediaError("Generated ambient score failed its audio stream or duration check.")
    return target
