"""In-process upload indexing jobs.

Large uploads can outlive Railway/nginx request windows. This module keeps the
HTTP request short and runs the existing incremental indexer after the response.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

import structlog

logger = structlog.get_logger()

UploadJobStatus = Literal["queued", "processing", "ok", "error"]
UPLOAD_JOB_TTL_SECONDS = 24 * 60 * 60
MAX_UPLOAD_JOBS = 200


@dataclass
class UploadJob:
    job_id: str
    filename: str
    filepath: str
    tenant_id: str | None
    status: UploadJobStatus
    created_at: float
    updated_at: float
    documents_indexed: int = 0
    chunks_created: int = 0
    elapsed_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


_jobs: dict[str, UploadJob] = {}
_jobs_lock = threading.Lock()


def create_upload_job(*, filename: str, filepath: str, tenant_id: str | None) -> UploadJob:
    now = time.time()
    job = UploadJob(
        job_id=uuid4().hex,
        filename=filename,
        filepath=filepath,
        tenant_id=tenant_id,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    with _jobs_lock:
        _prune_jobs_locked(now)
        _jobs[job.job_id] = job
    return job


def get_upload_job(job_id: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if tenant_id is not None and job.tenant_id != tenant_id:
            return None
        return _job_to_dict(job)


def start_upload_job(job_id: str, filepath: str, metadata_overrides: dict[str, Any]) -> None:
    """Run upload indexing in the background and update job state."""
    start = time.time()
    _mark_processing(job_id)
    try:
        from app.rag.qa_chain import run_incremental_index

        result = run_incremental_index(
            filepath,
            llm_call_fn=None,
            metadata_overrides=metadata_overrides,
        )
        elapsed = time.time() - start
        if result.get("status") == "error":
            _mark_error(job_id, result.get("message", "Index failed"), result, elapsed)
            return
        _mark_ok(job_id, result, elapsed)
    except Exception as exc:
        elapsed = time.time() - start
        _mark_error(job_id, f"Index failed: {str(exc)[:100]}", elapsed_seconds=elapsed)


def _mark_processing(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "processing"
        job.updated_at = time.time()


def _mark_ok(job_id: str, result: dict[str, Any], elapsed_seconds: float) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "ok"
        job.documents_indexed = int(result.get("documents_indexed") or 1)
        job.chunks_created = int(result.get("chunks_created") or 0)
        job.elapsed_seconds = float(result.get("elapsed_seconds") or elapsed_seconds)
        job.warnings = list(result.get("warnings") or [])
        job.error = None
        job.updated_at = time.time()
    logger.info("upload_job_completed", job_id=job_id, chunks=job.chunks_created)


def _mark_error(
    job_id: str,
    error: str,
    result: dict[str, Any] | None = None,
    elapsed_seconds: float = 0.0,
) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "error"
        job.documents_indexed = int((result or {}).get("documents_indexed") or 0)
        job.chunks_created = int((result or {}).get("chunks_created") or 0)
        job.elapsed_seconds = float((result or {}).get("elapsed_seconds") or elapsed_seconds)
        job.warnings = list((result or {}).get("warnings") or [])
        job.error = error
        job.updated_at = time.time()
    logger.warning("upload_job_failed", job_id=job_id, error=error)


def _prune_jobs_locked(now: float) -> None:
    expired = [
        job_id
        for job_id, job in _jobs.items()
        if now - job.updated_at > UPLOAD_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        _jobs.pop(job_id, None)

    if len(_jobs) <= MAX_UPLOAD_JOBS:
        return
    removable = sorted(_jobs.values(), key=lambda job: job.updated_at)
    for job in removable[: len(_jobs) - MAX_UPLOAD_JOBS]:
        _jobs.pop(job.job_id, None)


def _job_to_dict(job: UploadJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "filename": job.filename,
        "documents_indexed": job.documents_indexed,
        "chunks_created": job.chunks_created,
        "elapsed_seconds": round(job.elapsed_seconds, 1),
        "warnings": list(job.warnings),
        "error": job.error,
    }
