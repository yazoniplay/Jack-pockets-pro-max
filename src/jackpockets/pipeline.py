"""Initial pipeline orchestration.

This milestone deliberately creates a reviewable job rather than pretending to
have researched or rendered a documentary. Real provider adapters and render
workers are introduced in subsequent milestones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .models import DocumentaryBrief, DocumentaryJob, JobStatus


def create_documentary_job(brief: DocumentaryBrief) -> DocumentaryJob:
    """Create a queued documentary job with an explicit next action."""
    return DocumentaryJob(
        id=str(uuid4()),
        status=JobStatus.QUEUED,
        brief=brief,
        created_at=datetime.now(UTC).isoformat(),
        message=(
            "Brief accepted. Research has not started; configure a research provider "
            "and run the research stage before drafting factual narration."
        ),
    )
