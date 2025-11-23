"""Logging configuration utilities.

Provides JSON-friendly logging configuration for the application and server.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """A simple JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string.

        Parameters
        ----------
        record: logging.LogRecord
            The log record to format.

        Returns
        -------
        str
            The formatted JSON log line.
        """

        payload: dict[str, Any] = {
            "level": record.levelname,
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "message": record.getMessage(),
            "name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(debug: bool) -> None:
    """Initialize application logging with JSON formatting.

    Parameters
    ----------
    debug: bool
        Whether to set the root logger to DEBUG level.
    """

    level: int = logging.DEBUG if debug else logging.INFO
    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove default handlers FastAPI/Uvicorn might add in certain run modes
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)

    # Tweak noisy loggers
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if not debug else level)
