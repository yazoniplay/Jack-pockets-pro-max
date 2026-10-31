"""SQLite persistence for documentary jobs and their audit trail."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings


@contextmanager
def _connect():
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                brief_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_job ON job_events(job_id, id);
            """
        )


def now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(job_id: str, brief: dict[str, Any]) -> dict[str, Any]:
    timestamp = now()
    with _connect() as db:
        db.execute(
            "INSERT INTO jobs(id,status,brief_json,created_at,updated_at) VALUES(?,?,?,?,?)",
            (job_id, "queued", json.dumps(brief), timestamp, timestamp),
        )
        db.execute(
            "INSERT INTO job_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (job_id, "job.created", json.dumps({"status": "queued"}), timestamp),
        )
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        events = db.execute(
            "SELECT event_type,payload_json,created_at FROM job_events "
            "WHERE job_id=? ORDER BY id",
            (job_id,),
        ).fetchall()
    item = dict(row)
    item["brief"] = json.loads(item.pop("brief_json"))
    item["result"] = json.loads(item.pop("result_json")) if item["result_json"] else None
    item["events"] = [
        {"type": event["event_type"], "payload": json.loads(event["payload_json"]),
         "created_at": event["created_at"]}
        for event in events
    ]
    return item


def list_jobs(limit: int = 25) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            "SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [job for row in rows if (job := get_job(row["id"])) is not None]


def update_job(
    job_id: str,
    status: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    timestamp = now()
    with _connect() as db:
        db.execute(
            "UPDATE jobs SET status=?,result_json=COALESCE(?,result_json),error=?,updated_at=? "
            "WHERE id=?",
            (status, json.dumps(result) if result is not None else None, error, timestamp, job_id),
        )
        db.execute(
            "INSERT INTO job_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (job_id, event_type, json.dumps(payload or {}), timestamp),
        )


def claim_job(job_id: str) -> bool:
    """Atomically claim a queued or failed job so duplicate requests cannot run it twice."""
    timestamp = now()
    with _connect() as db:
        cursor = db.execute(
            "UPDATE jobs SET status='planning',error=NULL,updated_at=? "
            "WHERE id=? AND status IN ('queued','failed')",
            (timestamp, job_id),
        )
        if cursor.rowcount != 1:
            return False
        db.execute(
            "INSERT INTO job_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (job_id, "pipeline.started", json.dumps({"stage": "multi_agent_planning"}), timestamp),
        )
        return True
