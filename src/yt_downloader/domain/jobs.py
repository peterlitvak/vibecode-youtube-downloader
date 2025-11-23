"""Domain models and in-memory job manager for download tasks."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Enumeration of download job statuses."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadRequest(BaseModel):
    """Request payload to start a download job."""

    url: str = Field(description="Video URL to download")
    formatId: str = Field(description="yt-dlp format identifier (itag/format_id)")
    targetDir: Optional[str] = Field(default=None, description="Target directory to store the file")


class JobSnapshot(BaseModel):
    """Serializable snapshot of a job's current state for API responses."""

    jobId: str = Field(description="Unique job identifier")
    status: JobStatus = Field(description="Current job status")
    progressPercent: float = Field(description="Download progress percent [0-100]")
    bytesDownloaded: int = Field(description="Bytes downloaded so far")
    totalBytes: Optional[int] = Field(default=None, description="Total bytes if known")
    filePath: Optional[str] = Field(default=None, description="Final file path if completed")
    error: Optional[str] = Field(default=None, description="Error message if failed")


@dataclass
class Job:
    """Internal job state tracked by the JobManager."""

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
        """Return a serializable snapshot of the job state."""

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
    """Simple in-memory job registry and coordination layer."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: Dict[str, set[Any]] = {}
        self._tasks: Dict[str, asyncio.Task[Any]] = {}

    async def create_job(self, url: str, format_id: str, target_dir: Path) -> Job:
        """Create and register a new job with QUEUED status."""

        job_id: str = uuid.uuid4().hex
        job: Job = Job(id=job_id, url=url, format_id=format_id, target_dir=target_dir)
        async with self._lock:
            self._jobs[job_id] = job
            self._subscribers.setdefault(job_id, set())
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by id."""

        async with self._lock:
            return self._jobs.get(job_id)

    async def set_task(self, job_id: str, task: asyncio.Task[Any]) -> None:
        """Associate an asyncio task with a job for cancellation and tracking."""

        async with self._lock:
            self._tasks[job_id] = task
            job = self._jobs.get(job_id)
            if job is not None:
                job.task = task

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job if possible."""

        async with self._lock:
            task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def subscribe(self, job_id: str, ws: Any) -> None:
        """Register a websocket subscriber for a job."""

        async with self._lock:
            self._subscribers.setdefault(job_id, set()).add(ws)

    async def unsubscribe(self, job_id: str, ws: Any) -> None:
        """Unregister a websocket subscriber."""

        async with self._lock:
            subs = self._subscribers.get(job_id)
            if subs and ws in subs:
                subs.remove(ws)

    async def broadcast(self, job_id: str, message: dict[str, Any]) -> None:
        """Send a message to all subscribers of a job."""

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
