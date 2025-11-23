"""Integration test for WebSocket progress endpoint using a stubbed downloader.

Patches the download runner to complete immediately to avoid network/yt-dlp.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Ensure src/ is importable before importing the app
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
_SRC_PATH: Path = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

# Prepare isolated environment for this test module
_TMP_BASE: Path = Path(tempfile.mkdtemp(prefix="ytdl_test_ws_base_"))
_ALWD: Path = _TMP_BASE / "allowed"
_HOST: Path = _TMP_BASE / "host"
_ALWD.mkdir(parents=True, exist_ok=True)
_HOST.mkdir(parents=True, exist_ok=True)

from fastapi.testclient import TestClient  # type: ignore  # imported after sys.path tweak
from yt_downloader.core.config import get_settings  # type: ignore
from yt_downloader.main import create_app  # type: ignore
from yt_downloader.domain.jobs import Job, JobStatus, manager  # type: ignore


async def _stub_run_download(job: Job, _manager) -> None:  # type: ignore[no-redef]
    """Immediately mark job as succeeded with a dummy file path inside allowed base."""
    job.file_path = _ALWD / "done.mp4"
    job.status = JobStatus.SUCCEEDED


class TestWebSocketIntegration(unittest.TestCase):
    """Tests for the WS endpoint delivering status and final messages."""

    def setUp(self) -> None:
        os.environ["DOWNLOADS_HOST_DIR"] = str(_HOST)
        get_settings.cache_clear()  # type: ignore[attr-defined]
        self.client: TestClient = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        os.environ.pop("DOWNLOADS_HOST_DIR", None)

    def test_ws_receives_initial_and_final(self) -> None:
        with patch("yt_downloader.api.http.run_download", _stub_run_download):
            # Create a job via API (no real download due to stub)
            payload: dict[str, str] = {
                "url": "https://www.youtube.com/watch?v=l0X3dJiVx1M",
                "formatId": "18",
            }
            resp = self.client.post("/api/download", json=payload)
            self.assertEqual(resp.status_code, 200, msg=f"Start failed: {resp.text}")
            job_id: str = resp.json()["jobId"]

            # Connect to WS and capture messages
            with self.client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
                first = ws.receive_json()
                self.assertIn(first.get("type"), {"status", "final"})
                # Expect a final message soon (loop ticks every 0.5s)
                final = ws.receive_json()
                self.assertEqual(final.get("type"), "final")
                self.assertEqual(final.get("status"), "succeeded")
                # In Docker, hostFilePath would be present; locally we just assert shape keys exist or are None
                self.assertIn("filePath", final)
