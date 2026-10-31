"""FastAPI application for Jack Pockets Pro Max."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import __version__
from .assets import AssetError, FootageCandidate, PexelsClient, download_pexels_video
from .config import get_settings
from .providers import configured_providers
from .schemas import CreateJobRequest, FootageSelectionRequest, JobSummary, NarrationRequest
from .storage import create_job as persist_job
from .storage import get_job, initialize_database, list_jobs, update_job
from .timeline import TimelineManifest
from .worker import run_job, run_narration_job, run_render_job


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


settings = get_settings()
app = FastAPI(
    title="Jack Pockets Pro Max",
    description="An AI-assisted documentary video generation API.",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict:
    providers = configured_providers()
    return {
        "status": "ok",
        "version": __version__,
        "configured_providers": sorted(providers),
        "pipeline": "multi_agent_planning+narration+remotion_render",
    }


@app.get("/api/providers")
def provider_status() -> dict:
    providers = configured_providers()
    return {
        "providers": [
            {"name": name, "configured": True, "model": provider.model}
            for name, provider in providers.items()
        ],
        "collaboration_ready": len(providers) >= 2,
        "note": "ChatGPT app access does not supply an OpenAI API key.",
    }


@app.post("/api/jobs", response_model=JobSummary, status_code=202)
async def create_job(request: CreateJobRequest, background_tasks: BackgroundTasks) -> dict:
    brief = request.brief.model_dump(mode="json")
    job_id = str(uuid4())
    job = persist_job(job_id, brief)
    if request.start_collaboration:
        background_tasks.add_task(run_job, job_id, brief)
    return job


@app.get("/api/jobs", response_model=list[JobSummary])
def jobs(limit: int = Query(default=25, ge=1, le=100)) -> list[dict]:
    return list_jobs(limit)


@app.get("/api/jobs/{job_id}", response_model=JobSummary)
def job_detail(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Documentary job not found.")
    return job


@app.post("/api/jobs/{job_id}/run", response_model=JobSummary, status_code=202)
async def start_job(job_id: str, background_tasks: BackgroundTasks) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Documentary job not found.")
    if job["status"] not in {"queued", "failed"}:
        raise HTTPException(status_code=409, detail=f"Job cannot run from state {job['status']}.")
    background_tasks.add_task(run_job, job_id, job["brief"])
    return job


@app.get("/api/assets/search")
async def search_footage(
    query: str = Query(min_length=1, max_length=160),
    limit: int = Query(default=12, ge=1, le=30),
) -> dict:
    try:
        client = PexelsClient()
        candidates = await client.search_videos(query, per_page=limit)
    except AssetError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Pexels footage search failed.") from exc
    return {
        "provider": "pexels",
        "license": "Pexels License",
        "results": [candidate.__dict__ for candidate in candidates],
    }


@app.post("/api/jobs/{job_id}/narration", response_model=JobSummary, status_code=202)
async def start_narration(
    job_id: str,
    request: NarrationRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Documentary job not found.")
    if job["status"] != "needs_review":
        raise HTTPException(
            status_code=409,
            detail="Narration requires a planning result in needs_review state.",
        )
    update_job(
        job_id,
        "narrating",
        "narration.started",
        {"voice": request.voice, "fps": request.fps},
    )
    background_tasks.add_task(
        run_narration_job, job_id, request.text, request.voice, request.fps
    )
    return get_job(job_id)


@app.post("/api/jobs/{job_id}/render", response_model=JobSummary, status_code=202)
async def start_render(
    job_id: str,
    manifest: TimelineManifest,
    background_tasks: BackgroundTasks,
) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Documentary job not found.")
    if job["status"] != "needs_review":
        raise HTTPException(
            status_code=409,
            detail="Rendering requires a reviewed planning/narration job.",
        )
    manifest_data = manifest.model_dump(mode="json")
    update_job(
        job_id,
        "rendering",
        "render.started",
        {"scene_count": len(manifest.scenes), "fps": manifest.fps},
    )
    background_tasks.add_task(run_render_job, job_id, manifest_data)
    return get_job(job_id)


@app.get("/api/jobs/{job_id}/video")
def download_video(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Documentary job not found.")
    output_path = (job.get("result") or {}).get("render", {}).get("output_path")
    if job["status"] != "completed" or not output_path:
        raise HTTPException(status_code=409, detail="The documentary render is not complete.")
    target = Path(output_path).resolve()
    render_dir = (Path(__file__).resolve().parents[2] / "renders").resolve()
    if not target.is_relative_to(render_dir) or not target.is_file():
        raise HTTPException(status_code=404, detail="Rendered video file is unavailable.")
    return FileResponse(
        target,
        media_type="video/mp4",
        filename=f"jack-pockets-{job_id}.mp4",
    )


@app.post("/api/jobs/{job_id}/assets")
async def select_footage(job_id: str, request: FootageSelectionRequest) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Documentary job not found.")
    if job["status"] not in {"needs_review", "narrating"}:
        raise HTTPException(status_code=409, detail="Footage can only be added during editorial review.")
    candidate = FootageCandidate(
        provider="pexels",
        provider_id=request.provider_id,
        title=request.title,
        creator=request.creator,
        page_url=str(request.page_url),
        download_url=str(request.media_uri),
        width=request.width,
        height=request.height,
        duration_seconds=request.duration_seconds,
        license_name="Pexels License",
        license_url=PexelsClient.LICENSE_URL,
    )
    relative_path = f"assets/{job_id}/pexels-{request.provider_id}.mp4"
    try:
        saved = await download_pexels_video(
            candidate, Path("renderer") / "public" / relative_path
        )
    except AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Pexels media download failed.") from exc

    asset_record = {
        "provider": "pexels",
        "provider_id": request.provider_id,
        "title": request.title,
        "creator": request.creator,
        "source_url": str(request.page_url),
        "local_file": relative_path,
        "width": request.width,
        "height": request.height,
        "duration_seconds": request.duration_seconds,
        "license_name": "Pexels License",
        "license_url": PexelsClient.LICENSE_URL,
        "bytes": saved.stat().st_size,
    }
    payload = dict(job.get("result") or {})
    assets = list(payload.get("assets") or [])
    assets.append(asset_record)
    payload["assets"] = assets
    update_job(job_id, job["status"], "asset.selected", {"provider_id": request.provider_id}, result=payload)
    return asset_record
