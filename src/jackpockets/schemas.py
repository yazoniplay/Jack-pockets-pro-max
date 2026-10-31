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


class NarrationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    voice: str = Field(default="en-US-AriaNeural", min_length=3, max_length=100)
    fps: int = Field(default=30, ge=24, le=60)
