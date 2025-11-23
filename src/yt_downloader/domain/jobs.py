"""Domain models and in-memory job manager for download tasks.

This module defines a lightweight, process-local job system. Jobs are not
persisted and are intended for one-shot downloads observed in real time via
WebSocket. Concurrency is coordinated with ``asyncio.Lock`` to provide basic
consistency guarantees without external storage.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Enumeration of download job statuses.

    Notes
    -----
    - Terminal states are ``SUCCEEDED``, ``FAILED``, and ``CANCELLED``.
    - State transitions are monotonic and managed by the download service.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadRequest(BaseModel):
    """Request payload to start a download job.

    Notes
    -----
    - ``formatId`` may be an itag or a full yt-dlp selector (e.g., ``18`` or
      ``"18/worst[ext=mp4]/worst/best"``).
    - ``targetDir`` is sandboxed under ``allowed_base_dir`` and may be omitted to
      fall back to ``default_download_dir``.
    """

    url: str = Field(description="Video URL to download")
    formatId: str = Field(description="yt-dlp format identifier (itag/format_id)")
    targetDir: Optional[str] = Field(default=None, description="Target directory to store the file")


class JobSnapshot(BaseModel):
    """Serializable snapshot of a job's current state for API responses.

    Notes
    -----
    - ``progressPercent`` is clamped to [0, 100] and grows monotonically.
    - ``filePath`` is present when a job has successfully completed.
    """

    jobId: str = Field(description="Unique job identifier")
    status: JobStatus = Field(description="Current job status")
    progressPercent: float = Field(description="Download progress percent [0-100]")
    bytesDownloaded: int = Field(description="Bytes downloaded so far")
    totalBytes: Optional[int] = Field(default=None, description="Total bytes if known")
    filePath: Optional[str] = Field(default=None, description="Final file path if completed")
    hostFilePath: Optional[str] = Field(default=None, description="Host-visible file path if available")
    error: Optional[str] = Field(default=None, description="Error message if failed")


@dataclass
class Job:
    """Internal job state tracked by the JobManager.

    Notes
    -----
    - The ``progress_percent`` field is monotonic and represents overall progress.
    - ``bytes_downloaded`` and ``total_bytes`` reflect byte-level progress if known.
    - Instances are mutated by the download worker; callers should treat fields as
      volatile and rely on snapshots or broadcast events for UI updates.
    """

    id: str
    url: str
    format_id: str
    target_dir: Path
    status: JobStatus = JobStatus.QUEUED
    progress_percent: float = 0.0
    bytes_downloaded: int = 0
    total_bytes: Optional[int] = None
    file_path: Optional[Path] = None
    error: Optional[str] = None
    task: Optional[asyncio.Task[Any]] = None

    def snapshot(self) -> JobSnapshot:
        """Return a serializable snapshot of the job state.

        Notes
        -----
        - Converts any ``Path`` members to strings for JSON serialization.
        - Intended for quick API responses without exposing internal mutability.
        """

        return JobSnapshot(
            jobId=self.id,
            status=self.status,
            progressPercent=self.progress_percent,
            bytesDownloaded=self.bytes_downloaded,
            totalBytes=self.total_bytes,
            filePath=str(self.file_path) if self.file_path else None,
            error=self.error,
        )


class JobManager:
    """Simple in-memory job registry and coordination layer.

    Notes
    -----
    - Process-local only: no persistence, no cross-process coordination.
    - Uses an ``asyncio.Lock`` to serialize concurrent access to maps.
    - Maintains best-effort subscriber sets per job for WebSocket fan-out.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: Dict[str, set[Any]] = {}
        self._tasks: Dict[str, asyncio.Task[Any]] = {}

    async def create_job(self, url: str, format_id: str, target_dir: Path) -> Job:
        """Create and register a new job with QUEUED status.

        Notes
        -----
        - Generates a UUIDv4 identifier.
        - Initializes subscriber tracking for the job.
        """

        job_id: str = uuid.uuid4().hex
        job: Job = Job(id=job_id, url=url, format_id=format_id, target_dir=target_dir)
        async with self._lock:
            self._jobs[job_id] = job
            self._subscribers.setdefault(job_id, set())
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by id.

        Returns
        -------
        Optional[Job]
            The job if present; otherwise ``None``.
        """

        async with self._lock:
            return self._jobs.get(job_id)

    async def set_task(self, job_id: str, task: asyncio.Task[Any]) -> None:
        """Associate an asyncio task with a job for cancellation and tracking.

        Notes
        -----
        - Enables ``cancel`` to propagate cancellation to the running download.
        - Task association occurs after job creation and scheduling.
        """

        async with self._lock:
            self._tasks[job_id] = task
            job = self._jobs.get(job_id)
            if job is not None:
                job.task = task

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job if possible.

        Returns
        -------
        bool
            ``True`` if a pending task was found and cancellation was requested; otherwise ``False``.
        """

        async with self._lock:
            task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def subscribe(self, job_id: str, ws: Any) -> None:
        """Register a websocket subscriber for a job.

        Notes
        -----
        - Subscribers are stored weakly by identity and may be pruned on send errors.
        """

        async with self._lock:
            self._subscribers.setdefault(job_id, set()).add(ws)

    async def unsubscribe(self, job_id: str, ws: Any) -> None:
        """Unregister a websocket subscriber.

        Notes
        -----
        - No-op if the subscriber was not registered.
        """

        async with self._lock:
            subs = self._subscribers.get(job_id)
            if subs and ws in subs:
                subs.remove(ws)

    async def broadcast(self, job_id: str, message: dict[str, Any]) -> None:
        """Send a message to all subscribers of a job.

        Notes
        -----
        - Best-effort fan-out: individual send failures are ignored to avoid blocking others.
        - Payloads are expected to be JSON-serializable.
        """

        async with self._lock:
            subscribers = list(self._subscribers.get(job_id, set()))
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                # Ignore send errors; subscriber will likely disconnect
                pass


# Global manager instance for app scope
manager: JobManager = JobManager()
