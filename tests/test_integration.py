"""Integration tests for the YouTube Downloader service.

These tests exercise the running FastAPI app in-memory using TestClient.
They require internet access for the probe test against a stable YouTube test video.
"""
from __future__ import annotations

import sys
import unittest
import os
import tempfile
import time
from pathlib import Path
from typing import Any

# Ensure the src/ path is importable for the tests and configure env before importing app
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
_SRC_PATH: Path = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

# Configure temporary download directory and allowed base before importing the app
_TEST_DL_DIR: Path = Path(tempfile.mkdtemp(prefix="ytdl_test_dl_"))
os.environ["YTD_ALLOWED_BASE_DIR"] = str(_TEST_DL_DIR)
os.environ["YTD_DEFAULT_DOWNLOAD_DIR"] = str(_TEST_DL_DIR)

from fastapi.testclient import TestClient  # type: ignore  # imported after sys.path tweak
from yt_downloader.main import app  # type: ignore  # imported after sys.path tweak


class TestIntegration(unittest.TestCase):
    """Integration tests for core endpoints."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a test client once for all tests."""

        cls.client: TestClient = TestClient(app)

    def test_health_endpoint(self) -> None:
        """GET /health returns an ok status payload."""

        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data: dict[str, Any] = resp.json()
        self.assertEqual(data.get("status"), "ok")

    def test_ui_root_serves_html(self) -> None:
        """GET / serves the index HTML page."""

        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        content_type: str | None = resp.headers.get("content-type")
        self.assertIsNotNone(content_type)
        self.assertIn("text/html", content_type or "")
        text: str = resp.text
        self.assertIn("YouTube Downloader", text)

    def test_probe_returns_formats_for_test_video(self) -> None:
        """POST /api/probe returns formats for a stable YouTube test video.

        Uses the user-provided URL: l0X3dJiVx1M.
        """

        payload: dict[str, str] = {
            "url": "https://www.youtube.com/watch?v=l0X3dJiVx1M",
        }
        resp = self.client.post("/api/probe", json=payload)
        # If networking is blocked, this may fail. The assertion helps surface it clearly.
        self.assertEqual(resp.status_code, 200, msg=f"Probe failed: {resp.text}")
        data: dict[str, Any] = resp.json()
        self.assertIn("formats", data)
        formats: list[dict[str, Any]] = data["formats"]
        self.assertIsInstance(formats, list)
        self.assertGreater(len(formats), 0)
        first: dict[str, Any] = formats[0]
        self.assertIn("id", first)

    def test_probe_rejects_invalid_url(self) -> None:
        """POST /api/probe returns 400 for invalid URLs."""

        payload: dict[str, str] = {"url": "notaurl"}
        resp = self.client.post("/api/probe", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_download_short_video_succeeds(self) -> None:
        """Start a download job for the provided 60s video and wait for completion.

        Uses a conservative format selector to prefer small/progressive MP4 when available.
        """

        url: str = "https://www.youtube.com/shorts/KxLS_0x_1kQ"
        # Prefer progressive MP4 360p (itag 18) if available; then smallest MP4; then worst/best
        format_selector: str = "18/worst[ext=mp4]/worst/best"
        payload: dict[str, str] = {
            "url": url,
            "formatId": format_selector,
            "targetDir": str(_TEST_DL_DIR),
        }

        start = self.client.post("/api/download", json=payload)
        self.assertEqual(start.status_code, 200, msg=f"Start failed: {start.text}")
        job_id: str = start.json()["jobId"]

        # Poll job status until success or timeout
        deadline: float = time.time() + 420.0
        last_status: str | None = None
        while time.time() < deadline:
            status_resp = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(status_resp.status_code, 200, msg=f"Status failed: {status_resp.text}")
            snap = status_resp.json()
            last_status = snap.get("status")
            if last_status == "succeeded":
                # Ensure a file path is provided
                self.assertTrue(snap.get("filePath"))
                break
            if last_status == "failed":
                self.fail(f"Download failed: {snap.get('error')}")
            time.sleep(1.0)

        self.assertEqual(last_status, "succeeded", msg=f"Job did not succeed. Last status: {last_status}")


if __name__ == "__main__":
    unittest.main()
