"""Multi-model roundtable: independent specialist work, cross-review, synthesis."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from .providers import LLMProvider, ModelReply, ProviderError


@dataclass
class AgentContribution:
    role: str
    provider: str
    model: str
    draft: str
    critique: str | None = None


@dataclass
class CollaborationResult:
    mode: str
    contributions: list[AgentContribution]
    synthesis: str
    warnings: list[str]


ROLE_PROMPTS = {
    "research_editor": (
        "You are the research editor. Build a documentary research brief. "
        "Separate established facts, disputed claims, unknowns and research questions. "
        "Never invent sources, quotes, statistics or URLs. Mark every unsupported claim."
    ),
    "story_architect": (
        "You are a documentary story architect. Design a compelling long-form narrative "
        "with a strong opening, clear causal logic, evidence-led chapters, transitions "
        "and a meaningful ending. Do not invent facts or quotations."
    ),
    "fact_checker": (
        "You are a skeptical documentary fact-checker. Identify overclaims, missing "
        "evidence, chronology errors, causal leaps, misleading framing and claims needing "
        "primary sources. Be specific and do not invent citations."
    ),
}


async def _safe_generate(provider: LLMProvider, system: str, prompt: str):
    try:
        return await provider.generate(system, prompt), None
    except (ProviderError, Exception) as exc:
        return None, f"{provider.name}: {type(exc).__name__}: {str(exc)[:300]}"


async def run_roundtable(
    providers: dict[str, LLMProvider],
    brief: dict,
) -> CollaborationResult:
    """Run distinct agents in parallel, then have a provider synthesize their work."""
    assignments = [
        ("research_editor", "gemini"),
        ("story_architect", "anthropic"),
        ("fact_checker", "openai"),
    ]
    available = [(role, providers[name]) for role, name in assignments if name in providers]
    if not available:
        raise ProviderError(
            "No AI providers are configured. Add at least one provider API key to .env."
        )

    prompt = (
        "DOCUMENTARY BRIEF\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\nReturn structured, detailed work. Clearly label assumptions and open questions."
    )
    results = await asyncio.gather(
        *[
            _safe_generate(provider, ROLE_PROMPTS[role], prompt)
            for role, provider in available
        ]
    )
    contributions: list[AgentContribution] = []
    warnings: list[str] = []
    for (role, provider), (reply, error) in zip(available, results):
        if error:
            warnings.append(error)
        elif reply:
            contributions.append(
                AgentContribution(role, reply.provider, reply.model, reply.text)
            )
    if not contributions:
        raise ProviderError("Every configured agent failed. " + "; ".join(warnings))

    # Cross-review: each successful specialist sees the other specialists' work.
    review_prompt = "\n\n".join(
        f"[{item.role} / {item.provider}]\n{item.draft}" for item in contributions
    )
    reviews = await asyncio.gather(
        *[
            _safe_generate(
                provider,
                "You are an independent reviewer. Critique the supplied work, "
                "identify contradictions and omissions, and recommend concrete fixes.",
                "Review the following agent contributions. Do not merely agree.\n\n"
                + review_prompt,
            )
            for _, provider in available
            if any(item.provider == provider.name for item in contributions)
        ]
    )
    for item, (reply, error) in zip(contributions, reviews):
        if reply:
            item.critique = reply.text
        elif error:
            warnings.append(error)

    synthesis_provider = providers.get("openai") or providers.get("anthropic") or providers.get("gemini")
    synthesis_prompt = (
        "Synthesize the specialist work and critiques into one coherent documentary "
        "development package. Resolve disagreements explicitly. Do not fabricate facts, "
        "sources or quotations. Keep unresolved issues in a section called OPEN QUESTIONS.\n\n"
        + review_prompt
        + "\n\nCRITIQUES\n"
        + "\n\n".join(
            f"[{item.role}]\n{item.critique or 'No critique returned.'}"
            for item in contributions
        )
    )
    synthesis, error = await _safe_generate(
        synthesis_provider,
        "You are the executive documentary editor. Produce the best defensible synthesis.",
        synthesis_prompt,
    )
    if error:
        warnings.append(error)
    final_text = synthesis.text if synthesis else (
        "Synthesis unavailable. Review the specialist contributions and retry."
    )
    mode = "multi_agent" if len(contributions) > 1 else "single_provider"
    if mode == "single_provider":
        warnings.append(
            "Only one provider completed work. This run is not genuine multi-model collaboration."
        )
    return CollaborationResult(mode, contributions, final_text, warnings)
