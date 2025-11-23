"""Unit tests for filesystem helpers in infra.fs."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional
import unittest

from yt_downloader.core.config import Settings
from yt_downloader.infra.fs import resolve_target_dir, to_host_display_path


class TestFS(unittest.TestCase):
    """Tests for resolve_target_dir and to_host_display_path."""

    def test_resolve_target_dir_default_creates(self) -> None:
        """When no path is provided, default dir is created and returned under base."""
        with tempfile.TemporaryDirectory() as td:
            root: Path = Path(td)
            base: Path = root / "base"
            default: Path = base / "dldef"
            settings: Settings = Settings(
                allowed_base_dir=base,
                default_download_dir=default,
                host_downloads_dir=None,
            )
            result: Path = resolve_target_dir(None, settings)
            self.assertTrue(result.exists())
            self.assertTrue(result.is_dir())
            self.assertEqual(result.resolve(), default.resolve())

    def test_resolve_target_dir_rejects_outside_base(self) -> None:
        """Reject a target path that is outside the allowed base directory."""
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            base: Path = Path(td1) / "base"
            base.mkdir(parents=True, exist_ok=True)
            outsider: Path = Path(td2)
            settings: Settings = Settings(
                allowed_base_dir=base,
                default_download_dir=base / "dldef",
                host_downloads_dir=None,
            )
            with self.assertRaises(ValueError):
                _ = resolve_target_dir(str(outsider), settings)

    def test_to_host_display_path_maps_into_host_root(self) -> None:
        """Map a container path under base to the corresponding host path when configured."""
        with tempfile.TemporaryDirectory() as td:
            root: Path = Path(td)
            base: Path = root / "container_dl"
            host: Path = root / "host_dl"
            base.mkdir(parents=True, exist_ok=True)
            host.mkdir(parents=True, exist_ok=True)
            file_in_container: Path = base / "sub" / "video.mp4"
            file_in_container.parent.mkdir(parents=True, exist_ok=True)
            settings: Settings = Settings(
                allowed_base_dir=base,
                default_download_dir=base,
                host_downloads_dir=host,
            )
            mapped: Optional[Path] = to_host_display_path(file_in_container, settings)
            self.assertIsNotNone(mapped)
            self.assertEqual(mapped.resolve(), (host / "sub" / "video.mp4").resolve())

    def test_to_host_display_path_none_when_not_configured(self) -> None:
        """Return None when host mapping is not configured or path is invalid."""
        with tempfile.TemporaryDirectory() as td:
            base: Path = Path(td) / "base"
            base.mkdir(parents=True, exist_ok=True)
            settings: Settings = Settings(
                allowed_base_dir=base,
                default_download_dir=base,
                host_downloads_dir=None,
            )
            out: Optional[Path] = to_host_display_path(base / "file.mp4", settings)
            self.assertIsNone(out)
