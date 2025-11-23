"""Download service orchestrating yt-dlp with progress broadcast."""
from __future__ import annotations

import asyncio
from pathlib import Path
import re
from typing import Any, Optional

from yt_dlp import YoutubeDL

from yt_downloader.core.config import Settings
from yt_downloader.domain.jobs import Job, JobManager, JobStatus


def _safe_percent(downloaded: int, total: Optional[int]) -> float:
    """Compute percentage safely."""

    if not total or total <= 0:
        return 0.0
    return max(0.0, min(100.0, (downloaded / total) * 100.0))


def _build_base_outtmpl(target_dir: Path) -> str:
    """Build a base outtmpl with title/id and resolution/FPS tokens."""

    # Include height and fps tokens; we'll resolve to a concrete path via prepare_filename
    # and then clean up missing tokens (None) before using a static outtmpl for download.
    return str(target_dir / "%(title)s-%(id)s-%(height)sp-%(fps)sfps.%(ext)s")


def _cleanup_missing_tokens(path: Path) -> Path:
    """Remove placeholders that became 'None' after prepare_filename."""

    s: str = str(path)
    s = s.replace("-Nonep", "")
    s = s.replace("-Nonefps", "")
    # Remove possible double separators created by cleanup
    s = re.sub(r"-{2,}", "-", s)
    s = s.replace(" - ", " ")
    return Path(s)


def _unique_path(p: Path) -> Path:
    """Return a unique path by appending ' (n)' if the file already exists."""

    if not p.exists():
        return p
    stem: str = p.stem
    suffix: str = p.suffix
    parent: Path = p.parent
    i: int = 1
    while True:
        candidate: Path = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _compute_final_outfile(url: str, format_selector: str, target_dir: Path) -> Path:
    """Use yt-dlp to render the final output file path and ensure uniqueness."""

    base_tmpl: str = _build_base_outtmpl(target_dir)
    probe_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": format_selector,
        "merge_output_format": "mp4",
        "outtmpl": base_tmpl,
    }
    with YoutubeDL(probe_opts) as ydl:
        info: dict[str, Any] = ydl.extract_info(url, download=False)
        rendered: str = ydl.prepare_filename(info)
    path: Path = Path(rendered)
    path = _cleanup_missing_tokens(path)
    return _unique_path(path)


def _compose_format(url: str, user_selector: str) -> str:
    """Compose a yt-dlp format string that ensures audio is present when needed.

    If the user provided a compound selector (contains "+" or "/"), return it as-is.
    Otherwise, probe the URL to check whether the selected format includes audio; if not,
    append a best-audio fallback so the final file has sound.

    Parameters
    ----------
    url: str
        The video URL.
    user_selector: str
        The user-selected format id or selector.

    Returns
    -------
    str
        A format selector string suitable for yt-dlp.
    """

    if "+" in user_selector or "/" in user_selector:
        return user_selector

    # Probe formats quickly to determine if the selected itag is progressive (has audio)
    probe_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    try:
        with YoutubeDL(probe_opts) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=False)
        for fmt in info.get("formats", []) or []:
            if str(fmt.get("format_id")) == user_selector:
                vcodec: str | None = fmt.get("vcodec")
                acodec: str | None = fmt.get("acodec")
                if (vcodec and vcodec != "none") and (acodec and acodec != "none"):
                    return user_selector  # progressive, contains audio
                # Not progressive; combine with bestaudio and fallback to best
                return f"{user_selector}+bestaudio/best"
    except Exception:
        # If probing fails, fall back to a safe combined selector
        return f"{user_selector}+bestaudio/best"

    return user_selector


async def run_download(job: Job, manager: JobManager, settings: Settings) -> None:
    """Run the download using yt-dlp in a background thread and stream progress.

    Parameters
    ----------
    job: Job
        The job to execute.
    manager: JobManager
        In-memory job manager to broadcast progress.
    settings: Settings
        Application settings.
    """

    loop = asyncio.get_running_loop()

    def hook(d: dict[str, Any]) -> None:
        status: str = d.get("status", "")
        if status == "downloading":
            downloaded: int = int(d.get("downloaded_bytes") or 0)
            total_val = d.get("total_bytes") or d.get("total_bytes_estimate")
            total: Optional[int] = int(total_val) if total_val is not None else None
            job.bytes_downloaded = downloaded
            job.total_bytes = total
            # Compute progress percent; if total is unknown, fall back to elapsed/eta estimation
            percent: float = _safe_percent(downloaded, total)
            if (not total) or total <= 0:
                try:
                    elapsed = float(d.get("elapsed")) if d.get("elapsed") is not None else None
                    eta = float(d.get("eta")) if d.get("eta") is not None else None
                    # Only use ETA-based estimate when ETA is positive to avoid 100% spikes
                    if elapsed is not None and eta is not None and eta > 0 and (elapsed + eta) > 0:
                        est = (elapsed / (elapsed + eta)) * 100.0
                        # Never exceed 99% until final completion to avoid premature 100%
                        est = min(est, 99.0)
                        # Monotonic: do not regress
                        if est > percent:
                            percent = est
                except Exception:
                    pass
            # Monotonic overall
            if percent < job.progress_percent:
                percent = job.progress_percent
            job.progress_percent = percent
            # Fire and forget broadcast from worker thread
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(
                    job.id,
                    {
                        "type": "progress",
                        "progressPercent": job.progress_percent,
                        "bytesDownloaded": job.bytes_downloaded,
                        "totalBytes": job.total_bytes,
                        "speed": d.get("speed"),
                        "eta": d.get("eta"),
                    },
                ),
                loop,
            )
        elif status == "finished":
            # Download finished successfully
            filename: Optional[str] = d.get("filename")
            if filename:
                job.file_path = Path(filename)
            # Mark as complete
            job.progress_percent = 100.0
            job.status = JobStatus.SUCCEEDED
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(
                    job.id,
                    {
                        "type": "complete",
                        "filePath": str(job.file_path) if job.file_path else None,
                        "progressPercent": 100.0,
                    },
                ),
                loop,
            )

    format_selector: str = _compose_format(job.url, job.format_id)
    final_outfile: Path = _compute_final_outfile(job.url, format_selector, job.target_dir)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": False,
        "format": format_selector,
        "outtmpl": str(final_outfile),
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
    }

    job.status = JobStatus.RUNNING
    await manager.broadcast(job.id, {"type": "status", "status": job.status})

    def _blocking() -> None:
        with YoutubeDL(ydl_opts) as ydl:
            # Will raise on failure
            ydl.download([job.url])

    try:
        await asyncio.to_thread(_blocking)
        # If not already marked as succeeded by the hook, finalize now
        if job.status == JobStatus.RUNNING:
            job.status = JobStatus.SUCCEEDED
            job.progress_percent = 100.0  # Ensure progress is 100%
            await manager.broadcast(
                job.id,
                {
                    "type": "complete",
                    "filePath": str(job.file_path) if job.file_path else None,
                    "progressPercent": 100.0,
                },
            )
    except Exception as ex:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error = str(ex)
        await manager.broadcast(
            job.id,
            {"type": "error", "error": job.error, "progressPercent": job.progress_percent},
        )
