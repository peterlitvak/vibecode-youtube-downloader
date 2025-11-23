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

    Notes
    -----
    - Sandboxes writes under ``settings.allowed_base_dir`` via ``Path.relative_to`` to
      prevent escaping the approved area (e.g., ".." traversal or absolute paths).
    - Expands user input with ``expanduser()`` and ``resolve()`` before checks.
    - Creates the directory when missing; raises if the final path is not a directory.

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


def to_host_display_path(container_path: Path | None, settings: Settings) -> Path | None:
    """Translate a container path to a host-visible path for display/copy.

    Parameters
    ----------
    container_path: Path | None
        The file path inside the container (e.g., ``/downloads/video.mp4``).
    settings: Settings
        Application settings with ``allowed_base_dir`` and optional ``host_downloads_dir``.

    Returns
    -------
    Path | None
        The corresponding host path if mapping is configured; otherwise ``None``.

    Notes
    -----
    - When running in Docker, the app writes into ``allowed_base_dir`` (e.g., ``/downloads``)
      which is bind-mounted to a host directory (e.g., ``~/Downloads/ytdl``). If
      ``host_downloads_dir`` is set, this function returns the equivalent host path by
      computing the relative path from ``allowed_base_dir`` to the file and joining it to
      ``host_downloads_dir``.
    - Returns ``None`` when any input is missing or the file is outside the allowed base.
    """

    if container_path is None:
        return None
    host_root = settings.host_downloads_dir
    if host_root is None:
        return None

    base = settings.allowed_base_dir.expanduser().resolve()
    try:
        rel = container_path.expanduser().resolve().relative_to(base)
    except Exception:
        return None
    return host_root.expanduser().resolve() / rel
