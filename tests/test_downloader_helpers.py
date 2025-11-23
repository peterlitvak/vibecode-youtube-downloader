"""Unit tests for downloader helper functions."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional
import unittest
from unittest.mock import MagicMock, patch

from yt_downloader.services.downloader import (
    _safe_percent,
    _unique_path,
    _cleanup_missing_tokens,
    _compose_format,
)


class TestDownloaderHelpers(unittest.TestCase):
    """Tests for helper functions used by the downloader service."""

    def test_safe_percent_basics(self) -> None:
        """_safe_percent handles unknown totals and clamps correctly."""
        self.assertEqual(_safe_percent(10, None), 0.0)
        self.assertEqual(_safe_percent(10, 0), 0.0)
        self.assertEqual(_safe_percent(50, 100), 50.0)
        self.assertEqual(_safe_percent(150, 100), 100.0)
        self.assertEqual(_safe_percent(-10, 100), 0.0)

    def test_unique_path_appends_suffix(self) -> None:
        """_unique_path returns original if new; otherwise appends incrementing suffix."""
        with tempfile.TemporaryDirectory() as td:
            base: Path = Path(td) / "file.mp4"
            # Not exists yet
            res1: Path = _unique_path(base)
            self.assertEqual(res1, base)
            # Create and expect (1)
            base.write_text("")
            res2: Path = _unique_path(base)
            self.assertTrue(str(res2).endswith(" (1).mp4"))
            res2.write_text("")
            res3: Path = _unique_path(base)
            self.assertTrue(str(res3).endswith(" (2).mp4"))

    def test_cleanup_missing_tokens(self) -> None:
        """_cleanup_missing_tokens removes -Nonep and -Nonefps and squashes dashes."""
        p_in: Path = Path("/x/Title-Nonep-Nonefps-.mp4")
        p_out: Path = _cleanup_missing_tokens(p_in)
        self.assertEqual(str(p_out), "/x/Title-.mp4")

    def test_compose_format_returns_compound_as_is(self) -> None:
        """Compound selectors (+ or /) are returned unchanged."""
        self.assertEqual(_compose_format("https://x", "18+bestaudio/best"), "18+bestaudio/best")
        self.assertEqual(_compose_format("https://x", "18/worst"), "18/worst")

    @patch("yt_downloader.services.downloader.YoutubeDL")
    def test_compose_format_adds_bestaudio_when_video_only(self, ydl_mock: MagicMock) -> None:
        """When the selected itag is video-only, return `<itag>+bestaudio/best`."""
        # Mock extract_info to return a formats list with the chosen id lacking audio
        inst: MagicMock = ydl_mock.return_value.__enter__.return_value
        inst.extract_info.return_value = {
            "formats": [
                {"format_id": "18", "vcodec": "avc1", "acodec": "none"},
                {"format_id": "22", "vcodec": "avc1", "acodec": "mp4a"},
            ]
        }
        res: str = _compose_format("https://youtu.be/abc", "18")
        self.assertEqual(res, "18+bestaudio/best")

    @patch("yt_downloader.services.downloader.YoutubeDL")
    def test_compose_format_keeps_progressive(self, ydl_mock: MagicMock) -> None:
        """If the itag has both audio and video, return it unchanged."""
        inst: MagicMock = ydl_mock.return_value.__enter__.return_value
        inst.extract_info.return_value = {
            "formats": [
                {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a"},
            ]
        }
        res: str = _compose_format("https://youtu.be/abc", "18")
        self.assertEqual(res, "18")

    @patch("yt_downloader.services.downloader.YoutubeDL", side_effect=Exception("boom"))
    def test_compose_format_on_probe_failure(self, _: MagicMock) -> None:
        """On probe failure, fallback to `<itag>+bestaudio/best`."""
        res: str = _compose_format("https://youtu.be/abc", "18")
        self.assertEqual(res, "18+bestaudio/best")
