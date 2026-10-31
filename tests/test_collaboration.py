import asyncio

from jackpockets.collaboration import run_roundtable
from jackpockets.providers import ModelReply


class FakeProvider:
    def __init__(self, name: str):
        self.name = name
        self.model = f"fake-{name}"
        self.calls = 0

    async def generate(self, system: str, prompt: str) -> ModelReply:
        self.calls += 1
        return ModelReply(self.name, self.model, f"{self.name} contribution {self.calls}")


def test_three_providers_run_specialist_agents_and_cross_review() -> None:
    providers = {
        name: FakeProvider(name) for name in ("gemini", "ollama", "groq")
    }
    result = asyncio.run(
        run_roundtable(
            providers,
            {"topic": "How the printing press changed Europe", "target_minutes": 12},
        )
    )
    assert result.mode == "multi_agent"
    assert {item.role for item in result.contributions} == {
        "research_editor",
        "story_architect",
        "fact_checker",
    }
    assert all(item.critique for item in result.contributions)
    assert result.script_draft
    assert result.script_review
    assert all(provider.calls >= 2 for provider in providers.values())


def test_single_provider_is_never_mislabeled_as_collaboration() -> None:
    provider = FakeProvider("groq")
    result = asyncio.run(run_roundtable({"groq": provider}, {"topic": "Test"}))
    assert result.mode == "single_provider"
    assert result.script_draft
    assert result.script_review is None
    assert any("not genuine multi-model collaboration" in warning for warning in result.warnings)

class ScriptFailingGroq(FakeProvider):
    async def generate(self, system: str, prompt: str) -> ModelReply:
        self.calls += 1
        if "Write the complete narration script" in prompt:
            raise RuntimeError("script endpoint unavailable")
        return ModelReply(self.name, self.model, f"{self.name} contribution {self.calls}")


def test_narration_script_falls_back_when_primary_writer_fails() -> None:
    providers = {
        "gemini": FakeProvider("gemini"),
        "ollama": FakeProvider("ollama"),
        "groq": ScriptFailingGroq("groq"),
    }
    result = asyncio.run(
        run_roundtable(providers, {"topic": "Undersea internet cables", "target_minutes": 5})
    )
    assert result.script_draft
    assert any("Narration provider fallback" in warning for warning in result.warnings)
