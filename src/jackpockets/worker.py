"""Documentary planning worker. Rendering is deliberately a later pipeline stage."""

from __future__ import annotations

from .collaboration import run_roundtable
from .providers import configured_providers
from .storage import update_job


async def run_job(job_id: str, brief: dict) -> None:
    update_job(job_id, "planning", "pipeline.started", {"stage": "multi_agent_planning"})
    try:
        providers = configured_providers()
        result = await run_roundtable(providers, brief)
        payload = {
            "collaboration_mode": result.mode,
            "contributions": [
                {
                    "role": item.role,
                    "provider": item.provider,
                    "model": item.model,
                    "draft": item.draft,
                    "critique": item.critique,
                }
                for item in result.contributions
            ],
            "synthesis": result.synthesis,
            "warnings": result.warnings,
            "human_approval_required": True,
            "next_stage": "source_verification_and_script_approval",
        }
        update_job(
            job_id,
            "needs_review",
            "pipeline.review_ready",
            {"stage": "planning_complete", "collaboration_mode": result.mode},
            result=payload,
        )
    except Exception as exc:
        update_job(
            job_id,
            "failed",
            "pipeline.failed",
            {"stage": "planning", "error_type": type(exc).__name__},
            error=f"{type(exc).__name__}: {str(exc)[:1000]}",
        )
