"""WebSocket routes for streaming job progress events."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from yt_downloader.domain.jobs import JobStatus, manager
from yt_downloader.core.config import get_settings
from yt_downloader.infra.fs import to_host_display_path

router: APIRouter = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def ws_job_progress(websocket: WebSocket, job_id: str) -> None:
    """WebSocket endpoint to stream job progress events.

    Parameters
    ----------
    websocket: WebSocket
        The websocket connection.
    job_id: str
        The job identifier to subscribe to.

    Notes
    -----
    - Message types and payloads:
      - ``{"type":"status","status": <JobStatus>, "progressPercent": float, ...}`` initial snapshot.
      - ``{"type":"progress", ...}`` during download.
      - ``{"type":"complete", ...}`` when yt-dlp reports finished.
      - ``{"type":"final", ...}`` once a terminal state is observed (SUCCEEDED/FAILED/CANCELLED).
    - Lifecycle: the socket is kept open by a lightweight loop until a terminal
      state is reached or the client disconnects. Subscribers are automatically
      registered/unregistered against the in-memory manager.
    """

    await websocket.accept()
    settings = get_settings()
    await manager.subscribe(job_id, websocket)

    try:
        # Send initial snapshot if available
        job = await manager.get_job(job_id)
        if job is not None:
            host_path = to_host_display_path(job.file_path, settings)
            await websocket.send_json(
                {
                    "type": "status",
                    "status": job.status,
                    "progressPercent": job.progress_percent,
                    "bytesDownloaded": job.bytes_downloaded,
                    "totalBytes": job.total_bytes,
                    "filePath": str(job.file_path) if job.file_path else None,
                    "hostFilePath": str(host_path) if host_path else None,
                    "error": job.error,
                }
            )

        # Keep the socket open until job reaches a terminal state or disconnect
        while True:
            await asyncio.sleep(0.5)
            job = await manager.get_job(job_id)
            if job is None:
                break
            if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
                # Final snapshot to ensure completion state delivered
                host_path = to_host_display_path(job.file_path, settings)
                await websocket.send_json(
                    {
                        "type": "final",
                        "status": job.status,
                        "progressPercent": job.progress_percent,
                        "bytesDownloaded": job.bytes_downloaded,
                        "totalBytes": job.total_bytes,
                        "filePath": str(job.file_path) if job.file_path else None,
                        "hostFilePath": str(host_path) if host_path else None,
                        "error": job.error,
                    }
                )
                break
    except WebSocketDisconnect:
        # Client disconnected
        pass
    finally:
        await manager.unsubscribe(job_id, websocket)
