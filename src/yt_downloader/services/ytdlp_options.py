"""Shared yt-dlp option helpers."""
from __future__ import annotations

from typing import Any


def base_ytdlp_options() -> dict[str, Any]:
    """Return common yt-dlp options used by probe and download calls."""

    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "js_runtimes": {
            "deno": {},
            "node": {},
            "quickjs": {},
            "bun": {},
        },
    }
