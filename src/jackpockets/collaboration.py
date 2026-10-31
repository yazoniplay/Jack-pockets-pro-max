"""Multi-model roundtable: independent specialist work, cross-review, synthesis."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from .providers import LLMProvider, ProviderError


@dataclass
class AgentContribution:
    role: str
    provider: str
    model: str
    draft: str
    critique: str | None = None
    sources: list[dict[str, str]] = field(default_factory=list)


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
        "Prefer primary sources and recent authoritative sources. Never invent sources, "
        "quotes, statistics or URLs. Mark every unsupported claim."
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


async def _safe_generate(provider: LLMProvider, system: str, prompt: str, grounded: bool = False):
    try:
        if grounded and hasattr(provider, "generate_grounded"):
            reply = await provider.generate_grounded(system, prompt)
        else:
            reply = await provider.generate(system, prompt)
        return reply, None
    except Exception as exc:
        return None, f"{provider.name}: {type(exc).__name__}: {str(exc)[:300]}"


async def run_roundtable(
    providers: dict[str, LLMProvider],
    brief: dict,
) -> CollaborationResult:
    """Run specialist agents in parallel, cross-review their work, then synthesize."""
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
            _safe_generate(
                provider, ROLE_PROMPTS[role], prompt, grounded=(role == "research_editor")
            )
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
                AgentContribution(
                    role, reply.provider, reply.model, reply.text,
                    sources=getattr(reply, "sources", []),
                )
            )
    if not contributions:
        raise ProviderError("Every configured agent failed. " + "; ".join(warnings))

    review_prompt = "\n\n".join(
        f"[{item.role} / {item.provider}]\n{item.draft}" for item in contributions
    )
    review_assignments = [
        provider for _, provider in available
        if any(item.provider == provider.name for item in contributions)
    ]
    reviews = await asyncio.gather(
        *[
            _safe_generate(
                provider,
                "You are an independent reviewer. Critique the supplied work, identify "
                "contradictions and omissions, and recommend concrete fixes. Do not flatter.",
                "Review the following agent contributions. Do not merely agree.\n\n"
                + review_prompt,
            )
            for provider in review_assignments
        ]
    )
    for provider, (reply, error) in zip(review_assignments, reviews):
        item = next((entry for entry in contributions if entry.provider == provider.name), None)
        if item and reply:
            item.critique = reply.text
        elif error:
            warnings.append(error)

    synthesis_provider = (
        providers.get("openai") or providers.get("anthropic") or providers.get("gemini")
    )
    source_manifest = [
        {"agent": item.role, **source}
        for item in contributions
        for source in item.sources
    ]
    synthesis_prompt = (
        "Synthesize the specialist work and critiques into one coherent documentary "
        "development package. Resolve disagreements explicitly. Do not fabricate facts, "
        "sources or quotations. Cite only URLs in the supplied source manifest. Keep "
        "unresolved issues in a section called OPEN QUESTIONS.\n\n"
        + review_prompt
        + "\n\nSOURCE MANIFEST\n"
        + json.dumps(source_manifest, ensure_ascii=False, indent=2)
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
