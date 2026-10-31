"""Run the complete documentary pipeline in a GitHub Actions runner.

The workflow deliberately keeps all generated media in the runner and publishes it
as a GitHub Actions artifact; it does not require a continuously running web server.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jackpockets.assets import (
    AssetError,
    PexelsClient,
    download_pexels_video,
    evaluate_visual_candidates,
    rank_editorial_candidates,
)
from jackpockets.config import get_settings
from jackpockets.models import DocumentaryBrief
from jackpockets.narration import synthesize_narration
from jackpockets.providers import configured_providers
from jackpockets.rendering import render_documentary
from jackpockets.storage import create_job, initialize_database, update_job
from jackpockets.timeline import (
    TimelineAsset,
    TimelineCaption,
    TimelineManifest,
    TimelineScene,
)
from jackpockets.worker import run_job, run_narration_job, run_render_job


ROOT = Path(__file__).resolve().parents[1]
FPS = 30
VISUAL_REVIEW_LIMIT = 12


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:64] or "documentary").strip("-")


def write_srt(captions: list[dict], destination: Path, fps: int) -> None:
    def stamp(frame: int) -> str:
        milliseconds = round(frame / fps * 1000)
        hours, milliseconds = divmod(milliseconds, 3_600_000)
        minutes, milliseconds = divmod(milliseconds, 60_000)
        seconds, milliseconds = divmod(milliseconds, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    lines: list[str] = []
    for index, caption in enumerate(captions, start=1):
        lines.extend(
            [
                str(index),
                f"{stamp(caption['start_frame'])} --> {stamp(caption['end_frame'])}",
                caption["text"],
                "",
            ]
        )
    destination.write_text("\n".join(lines), encoding="utf-8")


async def build_timeline(job_id: str, job: dict, script: str) -> tuple[TimelineManifest, dict]:
    result = job.get("result") or {}
    storyboard_data = result.get("storyboard") or {}
    beats = storyboard_data.get("beats") or []
    if not beats:
        raise RuntimeError("The storyboard stage returned no beats.")

    providers = configured_providers()
    gemini = providers.get("gemini")
    pexels = PexelsClient()
    used_ids: set[str] = set()
    previous_id: str | None = None
    scenes: list[TimelineScene] = []
    selected_assets: list[dict] = []
    public_dir = ROOT / "renderer" / "public"
    asset_dir = public_dir / "assets" / job_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    for index, beat in enumerate(beats):
        query = str(beat["visual_query"])[:160]
        candidates = await pexels.search_videos(query, per_page=12)
        if not candidates:
            raise AssetError(f"No Pexels footage found for storyboard beat {beat['id']}: {query}")

        duration_seconds = max(
            1,
            (int(beat["end_frame"]) - int(beat["start_frame"])) / FPS,
        )
        ranked = rank_editorial_candidates(
            candidates,
            str(beat.get("narration_excerpt", "")),
            str(beat.get("visual_description", "")),
            query,
            duration_seconds,
        )
        visual_reviewed = False
        if gemini and index < VISUAL_REVIEW_LIMIT:
            ranked = await evaluate_visual_candidates(
                ranked,
                str(beat.get("narration_excerpt", "")),
                str(beat.get("visual_description", "")),
                query,
                gemini,
            )
            visual_reviewed = any(
                item.get("visual_evidence") == "gemini_preview_frame" for item in ranked
            )

        # Prefer a never-used clip. At minimum, never reuse the immediately previous clip.
        chosen = next(
            (item for item in ranked if item["provider_id"] not in used_ids),
            None,
        )
        if chosen is None:
            chosen = next(
                (item for item in ranked if item["provider_id"] != previous_id),
                None,
            )
        if chosen is None:
            raise AssetError(
                f"Could not find distinct footage for beat {beat['id']}; "
                "refusing to create adjacent repeated shots."
            )

        candidate = next(
            item for item in candidates if item.provider_id == chosen["provider_id"]
        )
        local_file = f"assets/{job_id}/pexels-{candidate.provider_id}.mp4"
        await download_pexels_video(candidate, public_dir / local_file)
        used_ids.add(candidate.provider_id)
        previous_id = candidate.provider_id

        scenes.append(
            TimelineScene(
                id=str(beat["id"]),
                kind="footage",
                duration_frames=int(beat["end_frame"]) - int(beat["start_frame"]),
                title=str(beat.get("visual_description") or beat["visual_query"])[:180],
                body=str(beat.get("editorial_reason") or "")[:600],
                eyebrow=str(beat.get("shot_type") or "DOCUMENTARY").upper()[:80],
                asset=TimelineAsset(
                    source_url=candidate.page_url,
                    local_file=local_file,
                    title=candidate.title,
                    creator=candidate.creator,
                    license_name=candidate.license_name,
                    license_url=candidate.license_url,
                ),
            )
        )
        selected_assets.append(
            {
                "beat_id": beat["id"],
                "query": query,
                "provider_id": candidate.provider_id,
                "title": candidate.title,
                "creator": candidate.creator,
                "source_url": candidate.page_url,
                "license": candidate.license_name,
                "license_url": candidate.license_url,
                "local_file": local_file,
                "editorial_score": chosen.get("editorial_score"),
                "semantic_score": chosen.get("semantic_score"),
                "technical_score": chosen.get("quality_score"),
                "visual_reviewed_by_gemini": visual_reviewed,
                "visual_evidence": chosen.get("visual_evidence", "not_reviewed"),
            }
        )
        print(
            f"[footage] {index + 1}/{len(beats)} selected Pexels clip "
            f"{candidate.provider_id} for {beat['id']}"
        )

    narration = result.get("narration") or {}
    captions = [
        TimelineCaption(
            start_frame=int(item["start_frame"]),
            end_frame=int(item["end_frame"]),
            text=str(item["text"])[:240],
        )
        for item in narration.get("captions", [])
        if str(item.get("text", "")).strip()
    ]
    manifest = TimelineManifest(
        title=str(job["brief"]["topic"])[:180],
        scenes=scenes,
        captions=captions,
        narration_file=str(narration["audio_path"]),
        music_enabled=True,
        fps=FPS,
        width=1920,
        height=1080,
    )
    return manifest, {
        "selected_assets": selected_assets,
        "visual_reviewed_beats": sum(
            item["visual_reviewed_by_gemini"] for item in selected_assets
        ),
        "total_beats": len(selected_assets),
    }


async def main(args: argparse.Namespace) -> Path:
    if not args.approve_generated_script:
        raise RuntimeError(
            "Automatic rendering is disabled. Re-run with "
            "APPROVE_GENERATED_SCRIPT=true after deciding to render the AI-generated script."
        )

    settings = get_settings()
    providers = configured_providers()
    missing = [name for name in ("gemini", "groq", "ollama") if name not in providers]
    if missing:
        raise RuntimeError(
            "Missing configured model providers: "
            + ", ".join(missing)
            + ". Add the matching GitHub Actions repository secrets."
        )
    if not settings.pexels_api_key:
        raise RuntimeError("PEXELS_API_KEY is required to source documentary footage.")

    brief = DocumentaryBrief(
        topic=args.topic,
        target_minutes=args.target_minutes,
        language=args.language,
        audience=args.audience,
        tone=args.tone,
        additional_context=args.additional_context,
    ).model_dump(mode="json")

    initialize_database()
    job_id = str(uuid4())
    create_job(job_id, brief)
    print(f"[job] Created documentary job {job_id}")

    await run_job(job_id, brief)
    from jackpockets.storage import get_job

    job = get_job(job_id)
    if not job or job["status"] != "needs_review":
        raise RuntimeError((job or {}).get("error") or "AI research and script generation failed.")
    result = job.get("result") or {}
    script = str(result.get("script_draft") or "").strip()
    if not script:
        raise RuntimeError("The AI roundtable did not produce a narration script.")

    output_dir = ROOT / "outputs" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "narration-script.md").write_text(script + "\n", encoding="utf-8")
    (output_dir / "editorial-review.md").write_text(
        "# AI editorial review\n\n"
        + str(result.get("script_review") or "No independent script review was returned.")
        + "\n\n## Warnings\n\n"
        + "\n".join(f"- {item}" for item in result.get("warnings", [])),
        encoding="utf-8",
    )
    print("[planning] AI research, cross-critique and narration draft complete")

    await run_narration_job(job_id, script, args.voice, FPS)
    job = get_job(job_id)
    if not job or job["status"] != "needs_review":
        raise RuntimeError((job or {}).get("error") or "Narration/storyboard generation failed.")
    print("[narration] Speech and timed captions generated")

    manifest, footage_report = await build_timeline(job_id, job, script)
    (output_dir / "timeline.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "footage-report.json").write_text(
        json.dumps(footage_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_srt(
        [item.model_dump() for item in manifest.captions],
        output_dir / "captions.srt",
        FPS,
    )
    print(
        f"[editing] Timeline assembled: {len(manifest.scenes)} shots; "
        f"Gemini visually reviewed {footage_report['visual_reviewed_beats']} beats"
    )

    update_job(
        job_id,
        "rendering",
        "render.started",
        {"scene_count": len(manifest.scenes), "fps": FPS, "music_mode": "generated_original_ambient"},
    )
    await run_render_job(job_id, manifest.model_dump(mode="json"))
    job = get_job(job_id)
    if not job or job["status"] != "completed":
        raise RuntimeError((job or {}).get("error") or "MP4 rendering or validation failed.")

    render = (job.get("result") or {}).get("render") or {}
    video_path = Path(render["output_path"])
    summary = [
        f"# {args.topic}",
        "",
        f"- Job: `{job_id}`",
        f"- Render: {render.get('width')}x{render.get('height')} at {render.get('frame_rate')} fps",
        f"- Duration: {render.get('duration_seconds')} seconds",
        f"- Size: {render.get('size_bytes')} bytes",
        f"- FFprobe validation: {render.get('validated')}",
        f"- Footage clips: {len(manifest.scenes)}",
        f"- Gemini visual reviews: {footage_report['visual_reviewed_beats']}/{footage_report['total_beats']}",
        "",
        "## Footage credits",
        *[
            f"- {item['title']} — {item['creator']} — {item['source_url']} "
            f"({item['license']}: {item['license_url']})"
            for item in footage_report["selected_assets"]
        ],
        "",
        "## Editorial note",
        "This is an AI-generated documentary draft. Review factual claims, source links, "
        "narration and footage before public release.",
    ]
    (output_dir / "documentary-report.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (output_dir / "job-result.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": job["status"],
                "brief": brief,
                "render": render,
                "source_manifest": (job.get("result") or {}).get("contributions", []),
                "warnings": (job.get("result") or {}).get("warnings", []),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"[complete] Validated documentary: {video_path}")
    return video_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a complete documentary MP4.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--target-minutes", type=int, default=5)
    parser.add_argument("--language", default="en")
    parser.add_argument("--audience", default="general")
    parser.add_argument("--tone", default="cinematic, evidence-led")
    parser.add_argument("--additional-context", default="")
    parser.add_argument("--voice", default="en-US-AriaNeural")
    parser.add_argument(
        "--approve-generated-script",
        action="store_true",
        default=os.getenv("APPROVE_GENERATED_SCRIPT", "").lower() == "true",
    )
    parsed = parser.parse_args()
    try:
        asyncio.run(main(parsed))
    except Exception as exc:  # noqa: BLE001 - fail the Actions job with a useful message
        print(f"::error::{type(exc).__name__}: {str(exc)[:1500]}", file=sys.stderr)
        raise SystemExit(1) from exc
