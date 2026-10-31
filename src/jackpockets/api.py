"""FastAPI application for Jack Pockets Pro Max."""

from fastapi import FastAPI

from . import __version__
from .models import DocumentaryBrief, DocumentaryJob
from .pipeline import create_documentary_job

app = FastAPI(
    title="Jack Pockets Pro Max",
    description="An AI-assisted documentary video generation API.",
    version=__version__,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/api/jobs", response_model=DocumentaryJob, status_code=202)
def create_job(brief: DocumentaryBrief) -> DocumentaryJob:
    """Accept a documentary brief and create a queued job."""
    return create_documentary_job(brief)
