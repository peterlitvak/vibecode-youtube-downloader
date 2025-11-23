"""Probe service using yt-dlp to extract video metadata and formats."""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from yt_downloader.domain.probe import FormatInfo, ProbeResponse


def _build_resolution(height: Optional[int]) -> Optional[str]:
    """Build a human-readable resolution string."""

    return f"{height}p" if height else None


def _normalize_format(fmt: dict[str, Any]) -> FormatInfo:
    """Normalize a yt-dlp format dict to FormatInfo."""

    fmt_id: str = str(fmt.get("format_id", ""))
    height: Optional[int] = fmt.get("height")
    resolution: Optional[str] = _build_resolution(height)
    fps: Optional[float] = fmt.get("fps")
    ext: Optional[str] = fmt.get("ext")
    vcodec: Optional[str] = fmt.get("vcodec")
    acodec: Optional[str] = fmt.get("acodec")
    note: Optional[str] = fmt.get("format_note") or fmt.get("format")

    return FormatInfo(
        id=fmt_id,
        resolution=resolution,
        fps=fps,
        ext=ext,
        vcodec=vcodec,
        acodec=acodec,
        note=note,
    )


def _validate_url(url: str) -> None:
    """Validate URL has a supported scheme and netloc."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL: only http(s) URLs are supported")


def probe_video(url: str) -> ProbeResponse:
    """Probe a video URL and return normalized metadata and formats.

    Parameters
    ----------
    url: str
        The video URL to probe.

    Returns
    -------
    ProbeResponse
        Normalized metadata and list of available formats.
    """

    _validate_url(url)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info: dict[str, Any] = ydl.extract_info(url, download=False)

    title: Optional[str] = info.get("title")
    dur_val = info.get("duration")
    duration_sec: Optional[int] = int(dur_val) if isinstance(dur_val, (int, float)) else None
    thumbnail: Optional[str] = info.get("thumbnail")

    raw_formats: list[dict[str, Any]] = list(info.get("formats", []))
    normalized_formats: list[FormatInfo] = [_normalize_format(f) for f in raw_formats]

    # Prefer highest resolution first if available
    def sort_key(f: FormatInfo) -> tuple[int, float]:
        height: int = int(f.resolution[:-1]) if f.resolution and f.resolution.endswith("p") else 0
        fps_val: float = float(f.fps) if f.fps is not None else 0.0
        return (-height, -fps_val)

    normalized_formats.sort(key=sort_key)

    response: ProbeResponse = ProbeResponse(
        title=title,
        durationSec=duration_sec,
        thumbnail=thumbnail,
        formats=normalized_formats,
    )
    return response
