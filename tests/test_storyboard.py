import asyncio
import json

import pytest
from pydantic import ValidationError

from jackpockets.providers import ModelReply
from jackpockets.storyboard import StoryboardError, StoryboardPlan, generate_storyboard


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
    plan = asyncio.run(
        generate_storyboard(
            "The city grew around the river. Trade routes connected distant markets.",
            600,
            30,
            provider,
        )
    )
    assert len(plan.beats) == 2
    assert plan.beats[0].narration_excerpt == "The city grew around the river."
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
