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
        name: FakeProvider(name) for name in ("gemini", "anthropic", "openai")
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
    assert all(provider.calls >= 2 for provider in providers.values())


def test_single_provider_is_never_mislabeled_as_collaboration() -> None:
    provider = FakeProvider("openai")
    result = asyncio.run(run_roundtable({"openai": provider}, {"topic": "Test"}))
    assert result.mode == "single_provider"
    assert any("not genuine multi-model collaboration" in warning for warning in result.warnings)
