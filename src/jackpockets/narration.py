"""Speech synthesis with timed word-boundary captions using Edge TTS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import shutil
import subprocess


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



def group_word_captions(
    words: list[WordCaption],
    fps: int,
    max_words: int = 7,
    max_duration_seconds: float = 2.8,
) -> list[WordCaption]:
    """Turn word timings into readable phrase captions without losing timing."""
    grouped: list[WordCaption] = []
    pending: list[WordCaption] = []

    def flush() -> None:
        if pending:
            grouped.append(
                WordCaption(
                    pending[0].start_frame,
                    pending[-1].end_frame,
                    " ".join(item.text for item in pending if item.text).strip(),
                )
            )
            pending.clear()

    for word in words:
        pending.append(word)
        elapsed = (pending[-1].end_frame - pending[0].start_frame) / fps
        closes_sentence = word.text.rstrip().endswith((".", "?", "!", ",", ";", ":"))
        if len(pending) >= max_words or elapsed >= max_duration_seconds or closes_sentence:
            flush()
    flush()
    return grouped


def estimate_word_captions(text: str, duration_frames: int, fps: int) -> list[WordCaption]:
    """Create approximate word timings when the speech service omits boundary events."""
    words = text.split()
    if not words or duration_frames <= 0:
        return []
    weights = [max(1, len(word)) for word in words]
    total_weight = sum(weights)
    cursor = 0
    timed_words: list[WordCaption] = []
    cumulative = 0
    for word, weight in zip(words, weights):
        start = round(cumulative / total_weight * duration_frames)
        cumulative += weight
        end = round(cumulative / total_weight * duration_frames)
        timed_words.append(
            WordCaption(start, max(start + 1, end), word)
        )
        cursor = end
    return timed_words


def probe_audio_duration_frames(audio_path: Path, fps: int) -> int | None:
    """Read the actual encoded audio duration with FFprobe when available."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        seconds = float(completed.stdout.strip())
        if math.isfinite(seconds) and seconds > 0:
            return max(1, round(seconds * fps))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


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
    word_captions = []
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
                    word_captions.append(
                        WordCaption(start, end, str(chunk.get("text", "")).strip())
                    )
                    last_end = max(last_end, end)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise NarrationError(f"Speech synthesis failed: {type(exc).__name__}: {str(exc)[:300]}") from exc

    if not target.is_file() or target.stat().st_size == 0:
        raise NarrationError("Speech provider returned no audio.")
    duration_frames = last_end
    captions = group_word_captions(word_captions, fps)
    if duration_frames <= 0:
        duration_frames = probe_audio_duration_frames(target, fps) or max(
            1, round(len(text.split()) / 135 * 60 * fps)
        )
        estimated_words = estimate_word_captions(text, duration_frames, fps)
        captions = group_word_captions(estimated_words, fps)
    if duration_frames <= 0:
        target.unlink(missing_ok=True)
        raise NarrationError("Could not determine a positive narration duration.")
    return NarrationResult(str(target), duration_frames, captions, voice, fps)
