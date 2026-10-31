"""Speech synthesis with timed word-boundary captions using Edge TTS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class NarrationError(RuntimeError):
    """Speech synthesis failed or its optional dependency is missing."""


@dataclass(frozen=True)
class WordCaption:
    start_frame: int
    end_frame: int
    text: str


@dataclass(frozen=True)
class NarrationResult:
    audio_path: str
    duration_frames: int
    captions: list[WordCaption]
    voice: str
    fps: int


async def synthesize_narration(
    text: str,
    output_path: str | Path,
    voice: str = "en-US-AriaNeural",
    fps: int = 30,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
) -> NarrationResult:
    """Generate MP3 narration and frame-accurate word captions.

    Edge TTS is an online service; this function requires network access.
    """
    if not text.strip():
        raise NarrationError("Narration text cannot be empty.")
    if len(text) > 100_000:
        raise NarrationError("Narration text exceeds the 100,000-character limit.")
    if not 24 <= fps <= 60:
        raise NarrationError("FPS must be between 24 and 60.")
    try:
        import edge_tts
    except ImportError as exc:
        raise NarrationError(
            "Install the optional speech dependency with: pip install -e '.[media]'"
        ) from exc

    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        text, voice, rate=rate, volume=volume, pitch=pitch
    )
    captions = []
    last_end = 0
    try:
        with target.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = max(0, round(chunk["offset"] / 10_000_000 * fps))
                    duration = max(1, round(chunk["duration"] / 10_000_000 * fps))
                    end = start + duration
                    captions.append(
                        WordCaption(start, end, str(chunk.get("text", "")).strip())
                    )
                    last_end = max(last_end, end)
    except Exception as exc:  # noqa: BLE001 - convert SDK errors to domain errors
        target.unlink(missing_ok=True)
        raise NarrationError(f"Speech synthesis failed: {type(exc).__name__}: {str(exc)[:300]}") from exc

    if not target.is_file() or target.stat().st_size == 0:
        raise NarrationError("Speech provider returned no audio.")
    return NarrationResult(str(target), last_end, captions, voice, fps)
