"""Upload golden corpus regression runner.

Usage:
  cd backend
  python tests/run_upload_regression.py --base-url https://aureon-production-659a.up.railway.app

The runner mutates the target environment by uploading 7 deterministic golden
files, then asserts each sentinel query returns its file at rank 1.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from tests.upload_golden_corpus import (  # noqa: E402
    UPLOAD_GOLDEN_CASES,
    create_upload_golden_files,
    evaluate_upload_search_results,
)


DEFAULT_BASE_URL = "https://aureon-production-659a.up.railway.app"


def run_upload_regression(
    *,
    base_url: str,
    token: str | None,
    output_dir: Path,
    top_k: int = 7,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aureon-upload-golden-") as temp_dir:
        files = create_upload_golden_files(Path(temp_dir))
        headers = _auth_headers(base_url, token)
        upload_results = _upload_all(base_url, headers, files)
        _clear_cache(base_url, headers)
        search_results = _search_all(base_url, headers, top_k=top_k)
        metrics = evaluate_upload_search_results(UPLOAD_GOLDEN_CASES, search_results)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base_url": base_url,
        "top_k": top_k,
        "uploads": upload_results,
        "search": search_results,
        "metrics": metrics,
    }
    report_path = output_dir / f"upload_regression_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _auth_headers(base_url: str, token: str | None) -> dict[str, str]:
    if token is None:
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{base_url}/api/security/demo-token")
            response.raise_for_status()
            token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_all(base_url: str, headers: dict[str, str], files: dict[str, Path]) -> list[dict[str, Any]]:
    uploads = []
    with httpx.Client(timeout=120, headers=headers) as client:
        for case in UPLOAD_GOLDEN_CASES:
            path = files[case.file_type]
            with path.open("rb") as fh:
                response = client.post(
                    f"{base_url}/api/rag/upload",
                    files={"file": (path.name, fh, "application/octet-stream")},
                    data={"language": "en", "title": path.name},
                )
            response.raise_for_status()
            payload = response.json()
            if payload.get("job_id") and payload.get("status") in {"queued", "processing"}:
                payload = _wait_upload_job(base_url, headers, payload["job_id"])
                if payload.get("status") == "error":
                    raise RuntimeError(payload.get("error") or "Upload indexing failed")
            uploads.append({
                "file_type": case.file_type,
                "filename": payload.get("filename"),
                "status": payload.get("status"),
                "chunks_created": payload.get("chunks_created"),
                "warnings": payload.get("warnings", []),
            })
    return uploads


def _wait_upload_job(
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    *,
    timeout_s: int = 600,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    with httpx.Client(timeout=30, headers=headers) as client:
        while time.monotonic() < deadline:
            response = client.get(f"{base_url}/api/rag/upload/status/{job_id}")
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") in {"ok", "error"}:
                return payload
            time.sleep(2)
    raise TimeoutError(f"Upload job timed out: {job_id}")


def _clear_cache(base_url: str, headers: dict[str, str]) -> None:
    with httpx.Client(timeout=30, headers=headers) as client:
        response = client.post(f"{base_url}/api/rag/cache/clear")
        response.raise_for_status()


def _search_all(base_url: str, headers: dict[str, str], *, top_k: int) -> dict[str, dict[str, Any]]:
    results = {}
    with httpx.Client(timeout=120, headers={**headers, "Content-Type": "application/json"}) as client:
        for case in UPLOAD_GOLDEN_CASES:
            response = client.post(
                f"{base_url}/api/rag/query",
                json={"query": case.query, "top_k": top_k, "use_mmr": False},
            )
            response.raise_for_status()
            payload = response.json()
            results[case.file_type] = {
                "query": case.query,
                "sources": payload.get("sources", []),
            }
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aureon upload golden corpus regression")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None, help="JWT bearer token. Default: request demo-token.")
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--top-k", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_upload_regression(
        base_url=args.base_url,
        token=args.token,
        output_dir=Path(args.output_dir),
        top_k=args.top_k,
    )
    metrics = report["metrics"]
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"Report: {report['report_path']}")
    return 0 if metrics["rank1_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
