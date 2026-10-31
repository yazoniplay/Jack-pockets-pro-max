"""Documentary planning worker. Rendering is deliberately a later pipeline stage."""

from __future__ import annotations

from .collaboration import run_roundtable
from .providers import configured_providers
from .storage import claim_job, get_job, update_job


async def generate_storyboard_with_fallback(
    script: str, duration_frames: int, fps: int, providers: dict
):
    """Try each configured model so one provider's formatting failure cannot stop editing."""
    from .storyboard import generate_storyboard

    warnings: list[str] = []
    ordered = [
        providers[name]
        for name in ("groq", "gemini", "ollama")
        if name in providers
    ]
    for provider in ordered:
        try:
            plan = await generate_storyboard(script, duration_frames, fps, provider)
            if warnings:
                warnings.append(
                    f"Storyboard fallback succeeded with {provider.name}."
                )
            return plan, warnings
        except Exception as exc:  # noqa: BLE001 - continue to the next configured provider
            warnings.append(
                f"{provider.name} storyboard attempt failed: "
                f"{type(exc).__name__}: {str(exc)[:300]}"
            )
    if not ordered:
        warnings.append("No model provider is configured to create the visual storyboard.")
    return None, warnings


async def run_job(job_id: str, brief: dict) -> None:
    if not claim_job(job_id):
        return
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
                    "sources": item.sources,
                }
                for item in result.contributions
            ],
            "synthesis": result.synthesis,
            "script_draft": result.script_draft,
            "script_review": result.script_review,
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
    except Exception as exc:  # noqa: BLE001 - persist any pipeline failure
        update_job(
            job_id,
            "failed",
            "pipeline.failed",
            {"stage": "planning", "error_type": type(exc).__name__},
            error=f"{type(exc).__name__}: {str(exc)[:1000]}",
        )


async def run_narration_job(job_id: str, text: str, voice: str, fps: int) -> None:
    from pathlib import Path

    from .narration import synthesize_narration

    try:
        result = await synthesize_narration(
            text,
            Path("renderer") / "public" / "assets" / job_id / "narration.mp3",
            voice=voice,
            fps=fps,
        )
        job = get_job(job_id)
        payload = dict(job.get("result") or {}) if job else {}
        payload["approved_script"] = text
        payload["narration"] = {
            "audio_path": f"assets/{job_id}/narration.mp3",
            "voice": result.voice,
            "fps": result.fps,
            "duration_frames": result.duration_frames,
            "captions": [
                {
                    "start_frame": item.start_frame,
                    "end_frame": item.end_frame,
                    "text": item.text,
                }
                for item in result.captions
            ],
        }
        providers = configured_providers()
        storyboard, storyboard_warnings = await generate_storyboard_with_fallback(
            text, result.duration_frames, fps, providers
        )
        if storyboard:
            payload["storyboard"] = storyboard.model_dump(mode="json")
        else:
            payload["storyboard"] = {"beats": []}
        if storyboard_warnings:
            payload["storyboard_warning"] = " | ".join(storyboard_warnings)
        payload["next_stage"] = "visual_timeline_assembly"
        update_job(
            job_id,
            "needs_review",
            "narration.completed",
            {
                "voice": voice,
                "caption_count": len(result.captions),
                "storyboard_beats": len(storyboard.beats) if storyboard else 0,
                "storyboard_warnings": storyboard_warnings,
            },
            result=payload,
        )
    except Exception as exc:  # noqa: BLE001 - persist any speech pipeline failure
        update_job(
            job_id,
            "failed",
            "narration.failed",
            {"error_type": type(exc).__name__},
            error=f"{type(exc).__name__}: {str(exc)[:1000]}",
        )


async def run_render_job(job_id: str, manifest_data: dict) -> None:
    from .rendering import render_documentary
    from .timeline import TimelineManifest

    try:
        manifest = TimelineManifest.model_validate(manifest_data)
        output_path, report = render_documentary(job_id, manifest)
        job = get_job(job_id)
        payload = dict(job.get("result") or {}) if job else {}
        payload["timeline"] = manifest.model_dump(mode="json")
        payload["render"] = {
            "output_path": str(output_path),
            "duration_seconds": report.duration_seconds,
            "width": report.width,
            "height": report.height,
            "video_codec": report.video_codec,
            "audio_codec": report.audio_codec,
            "frame_rate": report.frame_rate,
            "size_bytes": report.size_bytes,
            "validated": True,
            "music_mode": (
                "generated_original_ambient"
                if manifest.music_enabled and not manifest.music_file
                else "provided_audio" if manifest.music_enabled else "disabled"
            ),
        }
        payload["next_stage"] = "complete"
        update_job(
            job_id,
            "completed",
            "render.completed",
            {"duration_seconds": report.duration_seconds, "size_bytes": report.size_bytes},
            result=payload,
        )
    except Exception as exc:  # noqa: BLE001 - persist rendering and validation failures
        update_job(
            job_id,
            "failed",
            "render.failed",
            {"error_type": type(exc).__name__},
            error=f"{type(exc).__name__}: {str(exc)[:1500]}",
        )
