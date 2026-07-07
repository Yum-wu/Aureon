"""Tests for large upload job status storage."""

import json
from unittest.mock import MagicMock, patch

from app.rag import upload_jobs


def setup_function():
    upload_jobs._jobs.clear()


def test_create_upload_job_persists_status_to_redis():
    redis = MagicMock()

    with patch("app.rag.upload_jobs.get_sync_redis", return_value=redis):
        job = upload_jobs.create_upload_job(
            filename="large.csv",
            filepath="/tmp/large.csv",
            tenant_id="tenant-a",
        )

    redis.setex.assert_called_once()
    key, ttl, raw = redis.setex.call_args.args
    payload = json.loads(raw)
    assert key == f"{upload_jobs.UPLOAD_JOB_REDIS_PREFIX}{job.job_id}"
    assert ttl == upload_jobs.UPLOAD_JOB_TTL_SECONDS
    assert payload["status"] == "queued"
    assert payload["tenant_id"] == "tenant-a"


def test_get_upload_job_reads_redis_when_local_memory_is_empty():
    payload = {
        "job_id": "job-1",
        "filename": "large.csv",
        "filepath": "/tmp/large.csv",
        "tenant_id": "tenant-a",
        "status": "ok",
        "created_at": 1.0,
        "updated_at": 2.0,
        "documents_indexed": 1,
        "chunks_created": 285,
        "elapsed_seconds": 91.4,
        "warnings": [],
        "error": None,
    }
    redis = MagicMock()
    redis.get.return_value = json.dumps(payload).encode("utf-8")

    with patch("app.rag.upload_jobs.get_sync_redis", return_value=redis):
        result = upload_jobs.get_upload_job("job-1", tenant_id="tenant-a")

    assert result is not None
    assert result["status"] == "ok"
    assert result["chunks_created"] == 285


def test_get_upload_job_enforces_tenant_when_loaded_from_redis():
    payload = {
        "job_id": "job-1",
        "filename": "large.csv",
        "tenant_id": "tenant-a",
        "status": "ok",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    redis = MagicMock()
    redis.get.return_value = json.dumps(payload)

    with patch("app.rag.upload_jobs.get_sync_redis", return_value=redis):
        result = upload_jobs.get_upload_job("job-1", tenant_id="tenant-b")

    assert result is None
