"""Application configuration utilities.

This module defines application settings loaded from environment variables and
ensures required directories exist at startup.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from the environment.

    Notes
    -----
    - Environment variables are read with the ``YTD_`` prefix (e.g., ``YTD_CONCURRENT_FRAGMENTS``).
    - Paths are expanded with ``Path.expanduser()`` and used to sandbox writes under
      ``allowed_base_dir``. This prevents accidental writes outside the user-approved area.
    - A default downloads directory is created on startup; see ``ensure_directories``.
    """

    model_config = SettingsConfigDict(env_prefix="YTD_", env_file=".env", extra="ignore")

    app_name: str = Field(default="YouTube Downloader", description="Application display name")
    debug: bool = Field(default=False, description="Enable debug mode")
    default_download_dir: Path = Field(
        default=Path.home() / "Downloads" / "ytdl",
        description="Default directory where downloaded files are stored",
    )
    allowed_base_dir: Path = Field(
        default=Path.home() / "Downloads",
        description="Base directory under which downloads are allowed",
    )

    # Optional: absolute path on the host that maps to allowed_base_dir inside a container.
    # Used only for display so the UI can show a user-friendly path when the app runs in Docker.
    host_downloads_dir: Path | None = Field(
        default=None,
        description="Host path that backs the container downloads mount; used for display only",
    )

    concurrent_fragments: int = Field(
        default=5,
        description="Number of fragments to download concurrently when supported",
    )


def ensure_directories(settings: Settings) -> None:
    """Create required directories if they do not exist.

    Notes
    -----
    - Idempotent: safe to call multiple times.
    - Only ensures the default download directory exists; target directories provided at
      runtime are validated/created by ``infra.fs.resolve_target_dir``.

    Parameters
    ----------
    settings: Settings
        The resolved application settings instance.
    """

    directory: Path = settings.default_download_dir
    directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache application settings.

    Notes
    -----
    - Cached with ``functools.lru_cache(maxsize=1)`` to provide a single settings instance
      across the process. Subsequent calls return the same object.
    - Applies ``ensure_directories`` once to guarantee a sane startup state.

    Returns
    -------
    Settings
        The application settings instance.
    """

    settings: Settings = Settings()
    host_env: str | None = os.environ.get("DOWNLOADS_HOST_DIR")
    if host_env:
        settings.host_downloads_dir = Path(host_env).expanduser().resolve()
        downloads_path: Path = Path("/downloads")
        try:
            if downloads_path.exists() or os.access(downloads_path.parent, os.W_OK):
                settings.allowed_base_dir = downloads_path
                settings.default_download_dir = downloads_path
        except Exception:
            # Do not override on non-container environments without /downloads
            pass
    ensure_directories(settings)
    return settings
