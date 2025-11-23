"""Additional integration tests for API behavior.

Covers /health payload, 404 for unknown job, cancel unknown job, and
validation for targetDir outside allowed base.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

# Ensure src/ is importable before importing the app
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
_SRC_PATH: Path = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

# Prepare isolated environment
_TMP_BASE: Path = Path(tempfile.mkdtemp(prefix="ytdl_test_extra_base_"))
_ALWD: Path = _TMP_BASE / "allowed"
_DEF: Path = _ALWD / "default"
_HOST: Path = _TMP_BASE / "host"
_ALWD.mkdir(parents=True, exist_ok=True)
_HOST.mkdir(parents=True, exist_ok=True)

# Provide host mapping so /health exposes it (container-style)

from fastapi.testclient import TestClient  # type: ignore  # imported after sys.path tweak
from yt_downloader.core.config import get_settings  # type: ignore
from yt_downloader.main import create_app  # type: ignore


class TestIntegrationExtra(unittest.TestCase):
    """Integration tests for additional API surface."""

    def setUp(self) -> None:
        os.environ["DOWNLOADS_HOST_DIR"] = str(_HOST)
        get_settings.cache_clear()  # type: ignore[attr-defined]
        self.client: TestClient = TestClient(create_app())
        self.expected_host = _HOST.expanduser().resolve()

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        os.environ.pop("DOWNLOADS_HOST_DIR", None)

    def test_health_payload_includes_defaults(self) -> None:
        """/health returns status plus default and host download dirs when configured."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data: dict[str, Any] = resp.json()
        self.assertEqual(data.get("status"), "ok")
        # defaultDownloadDir should be present and a non-empty string
        self.assertIsInstance(data.get("defaultDownloadDir"), str)
        self.assertTrue(data.get("defaultDownloadDir"))
        # Normalize macOS /var vs /private/var by resolving both sides; compare to captured expected path
        got_host = data.get("hostDownloadsDir")
        self.assertIsInstance(got_host, str)
        self.assertEqual(Path(got_host).expanduser().resolve(), self.expected_host)

    def test_get_unknown_job_returns_404(self) -> None:
        """GET /api/jobs/{unknown} returns 404."""
        resp = self.client.get("/api/jobs/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_unknown_job_returns_false(self) -> None:
        """POST /api/jobs/{unknown}/cancel returns ok: false."""
        resp = self.client.post("/api/jobs/does-not-exist/cancel")
        self.assertEqual(resp.status_code, 200)
        data: dict[str, Any] = resp.json()
        self.assertFalse(data.get("ok"))

    def test_download_rejects_target_dir_outside_base(self) -> None:
        """POST /api/download rejects a targetDir outside the allowed base (400)."""
        payload: dict[str, str] = {
            "url": "https://www.youtube.com/watch?v=l0X3dJiVx1M",
            "formatId": "18",
            "targetDir": str(_TMP_BASE),  # outside of _ALWD
        }
        resp = self.client.post("/api/download", json=payload)
        self.assertEqual(resp.status_code, 400)
