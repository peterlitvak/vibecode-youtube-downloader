"""Filesystem helpers for validating and preparing target directories."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from yt_downloader.core.config import Settings


def resolve_target_dir(path_str: Optional[str], settings: Settings) -> Path:
    """Resolve and validate the target directory for downloads.

    Parameters
    ----------
    path_str: Optional[str]
        User-provided target directory path or None to use default.
    settings: Settings
        Application settings providing defaults and allowed base directory.

    Returns
    -------
    Path
        A resolved directory path that exists and is writable (creation attempted).

    Raises
    ------
    ValueError
        If the path is outside the allowed base directory or otherwise invalid.
    """

    base: Path = settings.allowed_base_dir.expanduser().resolve()
    if not path_str:
        target: Path = settings.default_download_dir.expanduser().resolve()
    else:
        target = Path(path_str).expanduser().resolve()

    try:
        target.relative_to(base)
    except ValueError as ex:
        raise ValueError("Target directory is outside the allowed base directory") from ex

    target.mkdir(parents=True, exist_ok=True)
    if not target.is_dir():
        raise ValueError("Target path is not a directory")

    return target
