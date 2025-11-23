"""FastAPI application entrypoint for the YouTube Downloader service."""
from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from yt_downloader.core.config import get_settings, Settings
from yt_downloader.core.logging import setup_logging
from yt_downloader.api.http import router as api_router
from yt_downloader.api.ws import router as ws_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

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
        """Serve the UI index page."""

        index_file: Path = templates_dir / "index.html"
        return FileResponse(index_file)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Health check endpoint.

        Returns
        -------
        dict[str, str]
            A simple status payload.
        """

        return {"status": "ok"}

    return app


app: Final[FastAPI] = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("yt_downloader.main:app", host="127.0.0.1", port=8000, reload=True)
