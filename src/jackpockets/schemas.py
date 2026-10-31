"""Public API response schemas."""

from pydantic import BaseModel, Field

from .models import DocumentaryBrief


class CreateJobRequest(BaseModel):
    brief: DocumentaryBrief
    start_collaboration: bool = False


class JobSummary(BaseModel):
    id: str
    status: str
    brief: dict
    created_at: str
    updated_at: str
    result: dict | None = None
    error: str | None = None
    events: list[dict] = Field(default_factory=list)
