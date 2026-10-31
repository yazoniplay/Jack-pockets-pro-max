"""AI-assisted storyboard planning from an approved narration script."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .providers import LLMProvider


class StoryboardBeat(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    narration_excerpt: str = Field(min_length=1, max_length=500)
    visual_query: str = Field(min_length=3, max_length=160)
    visual_description: str = Field(min_length=3, max_length=180)
    shot_type: Literal[
        "establishing", "detail", "archival", "map", "portrait", "process", "nature", "abstract"
    ]
    editorial_reason: str = Field(min_length=3, max_length=240)

    @model_validator(mode="after")
    def validate_frame_range(self):
        if self.end_frame - self.start_frame < 15:
            raise ValueError("Storyboard beats must be at least 15 frames long.")
        return self


class StoryboardPlan(BaseModel):
    duration_frames: int = Field(gt=0)
    fps: int = Field(ge=24, le=60)
    beats: list[StoryboardBeat] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_beat_order_and_bounds(self):
        previous_end = 0
        seen_ids = set()
        for beat in self.beats:
            if beat.id in seen_ids:
                raise ValueError(f"Duplicate storyboard beat id: {beat.id}")
            if beat.start_frame != previous_end:
                raise ValueError("Storyboard beats must be contiguous and cover the narration.")
            if beat.end_frame > self.duration_frames:
                raise ValueError("Storyboard beat extends beyond narration duration.")
            seen_ids.add(beat.id)
            previous_end = beat.end_frame
        if previous_end != self.duration_frames:
            raise ValueError("Storyboard beats must cover the complete narration duration.")
        return self


class StoryboardError(RuntimeError):
    """Storyboard generation or validation failed."""


async def generate_storyboard(
    script: str,
    duration_frames: int,
    fps: int,
    provider: LLMProvider,
) -> StoryboardPlan:
    if not script.strip():
        raise StoryboardError("An approved narration script is required for storyboarding.")
    if duration_frames <= 0 or not 24 <= fps <= 60:
        raise StoryboardError("Storyboard duration or frame rate is invalid.")

    prompt = (
        "Create a documentary visual storyboard synchronized to the supplied narration. "
        "Return ONLY valid JSON with this shape: "
        '{"duration_frames": integer, "fps": integer, "beats": ['
        '{"id": "beat-01", "start_frame": 0, "end_frame": 300, '
        '"narration_excerpt": "exact words copied from the script", '
        '"visual_query": "concise searchable stock-footage query", '
        '"visual_description": "what the viewer should see", '
        '"shot_type": "establishing|detail|archival|map|portrait|process|nature|abstract", '
        '"editorial_reason": "why this visual supports the narration"}]}. '
        f"Use exactly duration_frames={duration_frames} and fps={fps}. "
        "Create roughly one visual beat every 6–12 seconds, with more frequent changes "
        "when the narration changes subject. Beats must be ordered, non-overlapping, and "
        "inside the duration. Copy narration_excerpt verbatim from the supplied script; "
        "do not rewrite or invent dialogue. visual_query must describe real footage a stock "
        "library could contain. Never claim a specific archival clip exists. Vary shot types "
        "and avoid repetitive generic footage. If the narration describes a specific person, "
        "event or place, make the query precise; if evidence is uncertain, use a neutral visual. "
        "Cover the complete narration duration with beats.\n\nNARRATION SCRIPT\n"
        + script
    )
    try:
        reply = await provider.generate(
            "You are an award-winning documentary cinematographer and visual editor. "
            "Translate spoken meaning into precise, varied, evidence-respecting visual beats.",
            prompt,
        )
        raw = reply.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        if not raw.startswith("{"):
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("No JSON object found.")
            raw = raw[start : end + 1]
        plan = StoryboardPlan.model_validate(json.loads(raw))
    except Exception as exc:
        raise StoryboardError(
            f"Storyboard generation failed: {type(exc).__name__}: {str(exc)[:400]}"
        ) from exc

    if plan.duration_frames != duration_frames or plan.fps != fps:
        raise StoryboardError("Storyboard provider changed the supplied duration or frame rate.")
    return plan
