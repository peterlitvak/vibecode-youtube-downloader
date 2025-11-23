"""Application configuration utilities.

This module defines application settings loaded from environment variables and
ensures required directories exist at startup.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from the environment."""

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


def ensure_directories(settings: Settings) -> None:
    """Create required directories if they do not exist.

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

    Returns
    -------
    Settings
        The application settings instance.
    """

    settings: Settings = Settings()
    ensure_directories(settings)
    return settings
