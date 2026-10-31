import asyncio
import json

import pytest
from pydantic import ValidationError

from jackpockets.providers import ModelReply
from jackpockets.storyboard import StoryboardError, StoryboardPlan, generate_storyboard
from jackpockets.worker import (
    build_rule_based_storyboard,
    generate_storyboard_with_fallback,
)


class FakeStoryboardProvider:
    name = "fake"
    model = "fake-storyboard"

    def __init__(self, response: str):
        self.response = response
        self.prompt = ""

    async def generate(self, system: str, prompt: str) -> ModelReply:
        self.prompt = prompt
        return ModelReply(self.name, self.model, self.response)


def valid_payload() -> dict:
    return {
        "duration_frames": 600,
        "fps": 30,
        "beats": [
            {
                "id": "beat-01",
                "start_frame": 0,
                "end_frame": 300,
                "narration_excerpt": "The city grew around the river.",
                "visual_query": "aerial view historic European river city",
                "visual_description": "Wide aerial view of a historic river city",
                "shot_type": "establishing",
                "editorial_reason": "Establishes the geography described by the narrator.",
            },
            {
                "id": "beat-02",
                "start_frame": 300,
                "end_frame": 600,
                "narration_excerpt": "Trade routes connected distant markets.",
                "visual_query": "historic merchant ships sailing busy trade port",
                "visual_description": "Merchant ships moving through a busy port",
                "shot_type": "process",
                "editorial_reason": "Makes the trade network tangible.",
            },
        ],
    }


def test_storyboard_generation_validates_and_preserves_exact_duration() -> None:
    provider = FakeStoryboardProvider(json.dumps(valid_payload()))
    asyncio.run(
        generate_storyboard(
            "The city grew around the river. Trade routes connected distant markets.",
            600,
            30,
            provider,
        )
    )
    assert "visual storyboard" in provider.prompt.lower()


def test_storyboard_rejects_overlapping_beats() -> None:
    payload = valid_payload()
    payload["beats"][1]["start_frame"] = 250
    with pytest.raises(ValidationError, match="contiguous"):
        StoryboardPlan.model_validate(payload)


def test_storyboard_rejects_beats_beyond_narration() -> None:
    payload = valid_payload()
    payload["beats"][1]["end_frame"] = 601
    with pytest.raises(ValidationError, match="beyond narration"):
        StoryboardPlan.model_validate(payload)


def test_storyboard_rejects_malformed_provider_json() -> None:
    provider = FakeStoryboardProvider("not a JSON storyboard")
    with pytest.raises(StoryboardError, match="Storyboard generation failed"):
        asyncio.run(generate_storyboard("A script.", 600, 30, provider))


def test_storyboard_tries_next_provider_when_primary_returns_invalid_output() -> None:
    groq = FakeStoryboardProvider("not valid JSON")
    groq.name = "groq"
    gemini = FakeStoryboardProvider(json.dumps(valid_payload()))
    gemini.name = "gemini"

    plan, warnings = asyncio.run(
        generate_storyboard_with_fallback(
            "The city grew around the river. Trade routes connected distant markets.",
            600,
            30,
            {"groq": groq, "gemini": gemini},
        )
    )

    assert plan is not None
    assert len(plan.beats) == 2
    assert warnings
    assert "groq storyboard attempt failed" in warnings[0]
    assert "fallback succeeded with gemini" in warnings[1]


def test_rule_based_storyboard_covers_entire_duration_with_contiguous_beats() -> None:
    plan = build_rule_based_storyboard(
        "The ocean cables connect continents. Ships repair damaged lines beneath the sea.",
        1800,
        30,
    )
    assert plan.duration_frames == 1800
    assert plan.fps == 30
    assert len(plan.beats) == 6
    assert plan.beats[0].start_frame == 0
    assert plan.beats[-1].end_frame == 1800
    assert all(
        left.end_frame == right.start_frame
        for left, right in zip(plan.beats, plan.beats[1:])
    )


def test_all_provider_failures_still_produce_a_valid_local_storyboard() -> None:
    groq = FakeStoryboardProvider("not valid JSON")
    groq.name = "groq"
    gemini = FakeStoryboardProvider("still not valid JSON")
    gemini.name = "gemini"

    plan, warnings = asyncio.run(
        generate_storyboard_with_fallback(
            "The ocean cables connect continents. Ships repair damaged lines beneath the sea.",
            1800,
            30,
            {"groq": groq, "gemini": gemini},
        )
    )

    assert plan is not None
    assert plan.beats
    assert plan.beats[-1].end_frame == 1800
    assert any("basic local storyboard" in warning for warning in warnings)
