"""FastAPI application entrypoint for the YouTube Downloader service."""
from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from yt_downloader.core.config import get_settings, Settings
from yt_downloader.core.logging_cfg import setup_logging
from yt_downloader.api.http import router as api_router
from yt_downloader.api.ws import router as ws_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Notes
    -----
    - Serves static assets from ``/static`` and a single-page HTML UI from disk
      (no server-side templating).
    - Routers are included for HTTP APIs and WebSocket progress streaming.
    - Logging is configured up front based on settings; settings are loaded once.

    Returns
    -------
    FastAPI
        The configured FastAPI application.
    """

    settings: Settings = get_settings()
    setup_logging(settings.debug)

    app: FastAPI = FastAPI(title=settings.app_name)

    base_dir: Path = Path(__file__).parent
    ui_dir: Path = base_dir / "ui"
    templates_dir: Path = ui_dir / "templates"
    static_dir: Path = ui_dir / "static"

    # Static files
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(api_router)
    app.include_router(ws_router)

    @app.get("/", tags=["ui"])
    def index() -> FileResponse:
        """Serve the UI index page.

        Notes
        -----
        - Delivers a static HTML file; the frontend fetches APIs and opens a WebSocket.
        """

        index_file: Path = templates_dir / "index.html"
        return FileResponse(index_file)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Health check endpoint.

        Notes
        -----
        - Lightweight liveness probe intended for readiness checks; does not perform
          external calls.

        Returns
        -------
        dict[str, str]
            A simple status payload.
        """

        resp: dict[str, str] = {"status": "ok"}
        if settings.host_downloads_dir is not None:
            resp["hostDownloadsDir"] = str(settings.host_downloads_dir.expanduser().resolve())
        if settings.default_download_dir is not None:
            resp["defaultDownloadDir"] = str(settings.default_download_dir)
        return resp

    return app


app: Final[FastAPI] = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("yt_downloader.main:app", host="127.0.0.1", port=8000, reload=True)
