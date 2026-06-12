import os
import time

import pytest
import requests

BASE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
SAMPLE_ARCHIVE = os.path.join(os.path.dirname(__file__), "..", "sample_nested.zip")
TIMEOUT = 30  # seconds to wait for a job to complete

# Helpers

def wait_for_completion(job_id: str, timeout: int = TIMEOUT) -> dict:
    """Poll GET /extractions/{job_id} until status is completed or failed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{BASE_URL}/extractions/{job_id}", timeout=5)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.5)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


# Tests
class TestHealthEndpoint:
    def test_health_returns_200(self):
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestSubmitJob:
    def test_missing_file_returns_400(self):
        resp = requests.post(f"{BASE_URL}/extractions", data={"pattern": "*.txt"}, timeout=5)
        assert resp.status_code == 400

    def test_missing_pattern_returns_400(self):
        with open(SAMPLE_ARCHIVE, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/extractions",
                files={"file": f},
                timeout=5,
            )
        assert resp.status_code == 400

    def test_valid_submission_returns_202_with_job_id(self):
        with open(SAMPLE_ARCHIVE, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/extractions",
                files={"file": ("sample_nested.zip", f, "application/zip")},
                data={"pattern": "*.txt"},
                timeout=5,
            )
        assert resp.status_code == 202
        assert "job_id" in resp.json()


class TestFullFlow:
    """End-to-end: submit → wait → check results."""

    def test_nested_archive_finds_all_txt_files(self):
        # Submit job
        with open(SAMPLE_ARCHIVE, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/extractions",
                files={"file": ("sample_nested.zip", f, "application/zip")},
                data={"pattern": "*.txt"},
                timeout=5,
            )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Wait for completion
        status = wait_for_completion(job_id)
        assert status["status"] == "completed", f"Job failed: {status.get('error')}"

        # Fetch page 1 of results
        resp = requests.get(f"{BASE_URL}/extractions/{job_id}/results", timeout=5)
        assert resp.status_code == 200
        body = resp.json()

        matched_paths = [r["matched_path"] for r in body["data"]]

        # The sample archive has 4 .txt files across 3 nesting levels
        assert body["total"] == 4, f"Expected 4 matches, got {body['total']}. Paths: {matched_paths}"
        assert any("top_level.txt" in p for p in matched_paths)
        assert any("notes.txt" in p for p in matched_paths)
        assert any("deep.txt" in p for p in matched_paths)
        assert any("bottom.txt" in p for p in matched_paths)

    def test_pattern_with_no_matches_returns_zero_results(self):
        with open(SAMPLE_ARCHIVE, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/extractions",
                files={"file": ("sample_nested.zip", f, "application/zip")},
                data={"pattern": "*.exe"},
                timeout=5,
            )
        job_id = resp.json()["job_id"]
        status = wait_for_completion(job_id)
        assert status["status"] == "completed"

        resp = requests.get(f"{BASE_URL}/extractions/{job_id}/results", timeout=5)
        assert resp.json()["total"] == 0

    def test_unknown_job_id_returns_404(self):
        resp = requests.get(f"{BASE_URL}/extractions/nonexistent-id", timeout=5)
        assert resp.status_code == 404

    def test_pagination_page_param(self):
        with open(SAMPLE_ARCHIVE, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/extractions",
                files={"file": ("sample_nested.zip", f, "application/zip")},
                data={"pattern": "*.txt"},
                timeout=5,
            )
        job_id = resp.json()["job_id"]
        wait_for_completion(job_id)

        resp = requests.get(
            f"{BASE_URL}/extractions/{job_id}/results",
            params={"page": 1},
            timeout=5,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "page" in body
        assert "per_page" in body
        assert "total" in body
        assert "total_pages" in body
        assert isinstance(body["data"], list)
