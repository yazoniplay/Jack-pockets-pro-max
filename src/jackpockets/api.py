"""FastAPI application for Jack Pockets Pro Max."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .providers import configured_providers
from .schemas import CreateJobRequest, JobSummary
from .storage import create_job as persist_job
from .storage import get_job, initialize_database, list_jobs
from .worker import run_job


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
        "pipeline": "planning_foundation",
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
