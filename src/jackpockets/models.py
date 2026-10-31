"""Typed API models for documentary generation jobs."""

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field, HttpUrl


class JobStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class DocumentaryBrief(BaseModel):
    topic: str = Field(min_length=3, max_length=240)
    target_minutes: int = Field(default=10, ge=3, le=30)
    language: str = Field(default="en", min_length=2, max_length=12)
    audience: str = Field(default="general", max_length=120)
    tone: str = Field(default="cinematic, evidence-led", max_length=160)
    additional_context: str = Field(default="", max_length=3000)


class SourceRecord(BaseModel):
    title: str
    url: HttpUrl
    publisher: str | None = None
    published_at: str | None = None
    accessed_at: str | None = None


class ResearchClaim(BaseModel):
    claim: str
    source_urls: list[HttpUrl] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    needs_human_review: bool = False


class DocumentaryJob(BaseModel):
    id: str
    status: JobStatus
    brief: DocumentaryBrief
    created_at: str
    message: str
    research_claims: list[ResearchClaim] = Field(default_factory=list)
    source_records: list[SourceRecord] = Field(default_factory=list)
