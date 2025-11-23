"""Unit tests for the in-memory JobManager."""
from __future__ import annotations

import unittest
from typing import Any, Dict, List

from yt_downloader.domain.jobs import JobManager


class _CollectorWS:
    """A fake WebSocket that collects sent JSON messages."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    async def send_json(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)


class _FailingWS:
    """A fake WebSocket that raises on send to exercise error path."""

    async def send_json(self, message: Dict[str, Any]) -> None:  # noqa: ARG002
        raise Exception("boom")


class TestJobManager(unittest.IsolatedAsyncioTestCase):
    """Async tests for subscribe, broadcast, and unsubscribe semantics."""

    async def test_broadcast_to_multiple_and_ignore_failures(self) -> None:
        """Broadcast delivers to all subscribers and ignores individual failures."""
        mgr: JobManager = JobManager()
        ws1 = _CollectorWS()
        ws2 = _CollectorWS()
        bad = _FailingWS()
        job_id: str = "job1"

        await mgr.subscribe(job_id, ws1)
        await mgr.subscribe(job_id, ws2)
        await mgr.subscribe(job_id, bad)

        payload: Dict[str, Any] = {"hello": "world"}
        await mgr.broadcast(job_id, payload)

        self.assertEqual(ws1.messages, [payload])
        self.assertEqual(ws2.messages, [payload])

    async def test_unsubscribe_removes_subscriber(self) -> None:
        """Unsubscribe stops further deliveries to that subscriber."""
        mgr: JobManager = JobManager()
        ws1 = _CollectorWS()
        job_id: str = "job2"

        await mgr.subscribe(job_id, ws1)
        await mgr.broadcast(job_id, {"n": 1})
        self.assertEqual(len(ws1.messages), 1)

        await mgr.unsubscribe(job_id, ws1)
        await mgr.broadcast(job_id, {"n": 2})
        self.assertEqual(len(ws1.messages), 1)
