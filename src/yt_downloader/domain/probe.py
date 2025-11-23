"""Domain models for probing video metadata and formats.

These models define the request and response payloads for the probe API.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FormatInfo(BaseModel):
    """A single downloadable format entry returned by probing."""

    id: str = Field(description="yt-dlp format identifier (itag/format_id)")
    resolution: Optional[str] = Field(default=None, description="Human-readable resolution, e.g., 1080p")
    fps: Optional[float] = Field(default=None, description="Frames per second (may be fractional)")
    ext: Optional[str] = Field(default=None, description="Container/extension")
    vcodec: Optional[str] = Field(default=None, description="Video codec or 'none'")
    acodec: Optional[str] = Field(default=None, description="Audio codec or 'none'")
    note: Optional[str] = Field(default=None, description="Additional format note from yt-dlp")


class ProbeRequest(BaseModel):
    """Request payload to probe a video URL."""

    url: str = Field(description="Video URL to probe")


class ProbeResponse(BaseModel):
    """Response payload with normalized metadata and format list."""

    title: Optional[str] = Field(default=None, description="Video title if available")
    durationSec: Optional[int] = Field(default=None, description="Duration in seconds if available")
    thumbnail: Optional[str] = Field(default=None, description="Primary thumbnail URL if available")
    formats: list[FormatInfo] = Field(default_factory=list, description="List of available formats")
