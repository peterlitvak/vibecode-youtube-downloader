"""HTTP API routes for the YouTube Downloader service."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from yt_downloader.domain.probe import ProbeRequest, ProbeResponse
from yt_downloader.services.probe import probe_video
from yt_downloader.core.config import get_settings, Settings
from yt_downloader.infra.fs import resolve_target_dir
from yt_downloader.domain.jobs import (
    DownloadRequest,
    JobSnapshot,
    JobStatus,
    manager,
)
from yt_downloader.services.downloader import run_download

router: APIRouter = APIRouter(prefix="/api", tags=["api"])


@router.post("/probe", response_model=ProbeResponse)
def post_probe(payload: ProbeRequest) -> ProbeResponse:
    """Probe a video URL and return available formats.

    Parameters
    ----------
    payload: ProbeRequest
        The request payload containing the video URL.

    Returns
    -------
    ProbeResponse
        The normalized video metadata and formats.
    """

    try:
        response: ProbeResponse = probe_video(payload.url)
        return response
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as ex:  # noqa: BLE001 - surface a simple message to clients
        raise HTTPException(status_code=500, detail="Probe failed") from ex


@router.post("/download")
async def post_download(payload: DownloadRequest) -> dict[str, str]:
    """Start a one-shot download job and return the job id.

    Parameters
    ----------
    payload: DownloadRequest
        URL, format id/selector, and optional target directory.
    """

    settings: Settings = get_settings()
    try:
        target_dir: Path = resolve_target_dir(payload.targetDir, settings)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve

    job = await manager.create_job(url=payload.url, format_id=payload.formatId, target_dir=target_dir)

    task = asyncio.create_task(run_download(job, manager, settings))
    await manager.set_task(job.id, task)

    return {"jobId": job.id}


@router.get("/jobs/{job_id}", response_model=JobSnapshot)
async def get_job(job_id: str) -> JobSnapshot:
    """Return a snapshot of the job status."""

    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.snapshot()


@router.post("/jobs/{job_id}/cancel")
async def post_cancel(job_id: str) -> dict[str, Any]:
    """Attempt to cancel a running job."""

    ok: bool = await manager.cancel(job_id)
    return {"ok": ok}
