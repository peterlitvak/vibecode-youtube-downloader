# YouTube Downloader – Architecture & Delivery Plan

## 1) Goals and constraints

- No official YouTube API usage. Download via alternative method.
- Simple local-first app: backend service + minimal UI.
- UI elements: URL input, quality dropdown, target directory selector, progress display.
- Cross-platform where possible (macOS primary), small footprint, easy to run.

## 2) Technology choices

- Backend runtime: Python 3.11+
- Web framework: FastAPI (ASGI) + Uvicorn
- Download engine: yt-dlp (actively maintained fork of youtube-dl), using Python API
- Media tools: ffmpeg (required by yt-dlp for muxing/merging)
- Background execution: asyncio.create_task; progress hooks mapped to domain events
- Realtime updates: WebSocket (FastAPI) for progress streaming
- Persistence: none (one-shot; no history/database)
- Config: pydantic-settings
- Logging: JSON formatter to stdout + aligned Uvicorn loggers (configured once at app startup)
- Tests: unittest
- Packaging: Poetry (pyproject.toml)
- Containerization: Dockerfile + docker-compose (ffmpeg preinstalled), host downloads dir bind-mounted

## 3) System architecture

- Process model: single FastAPI process (Uvicorn). Jobs run in-process with cancellation and progress reporting.
- Modules
    - core/config.py – typed settings (YTD_ prefix; e.g., `YTD_CONCURRENT_FRAGMENTS`), container host mapping via
      `DOWNLOADS_HOST_DIR`. Locally defaults under `~/Downloads`; when `DOWNLOADS_HOST_DIR` is set (container),
      allowed/default dirs are `/downloads`.
    - core/logging_cfg.py – JSON logging setup for root and uvicorn loggers
    - domain/jobs.py – Job, JobStatus, JobSnapshot (includes hostFilePath), in-memory JobManager
    - domain/probe.py – Probe models
    - services/probe.py – fetch available formats/metadata via yt-dlp (download=False)
    - services/downloader.py – yt-dlp orchestration, progress hooks, audio merge fallback, unique filenames
    - infra/fs.py – resolve_target_dir (sandboxed) and to_host_display_path (container→host mapping)
    - api/http.py – REST endpoints (probe, start download, job status)
    - api/ws.py – WebSocket endpoint for live progress events (sends hostFilePath when available)
    - ui/ – static HTML + JS (Tailwind via CDN), dark mode toggle

### Directory layout

```
/ docs/plan.md
/ src/yt_downloader/__init__.py
/ src/yt_downloader/core/config.py
/ src/yt_downloader/core/logging_cfg.py
/ src/yt_downloader/domain/jobs.py
/ src/yt_downloader/domain/probe.py
/ src/yt_downloader/services/probe.py
/ src/yt_downloader/services/downloader.py
/ src/yt_downloader/infra/fs.py
/ src/yt_downloader/api/http.py
/ src/yt_downloader/api/ws.py
/ src/yt_downloader/ui/templates/index.html
/ src/yt_downloader/ui/static/app.js
/ src/yt_downloader/main.py
/ Dockerfile
/ docker-compose.yml
/ README.md
/ tests/ ...
/ pyproject.toml
/ poetry.lock
```

## 4) API design

- POST /api/probe
    - body: { url: string }
    - returns: { title, durationSec?, thumbnail?, formats: [{id, resolution, fps?, ext, vcodec, acodec, note}] }
- POST /api/download
    - body: { url: string, formatId: string, targetDir?: string }
    - returns: { jobId }
    - Notes: In Docker, `targetDir` is ignored; the server writes to `/downloads` (host-mapped).
- GET /api/jobs/{jobId}
    - returns: { status: "queued"|"running"|"succeeded"|"failed"|"cancelled", progressPercent, bytesDownloaded,
      filePath?, hostFilePath?, error? }
- POST /api/jobs/{jobId}/cancel
    - returns: { ok: true }
- WS /ws/jobs/{jobId}
    - server -> client events:
        - status: { type, status, progressPercent? }
        - progress: { type, progressPercent }
        - complete|final: { type, filePath?, hostFilePath? }
        - error: { type, error }
- GET /health
    - returns: { status: "ok", hostDownloadsDir?, defaultDownloadDir }

Notes

- `probe` is used to populate the quality dropdown. Use yt-dlp `extract_info(..., download=False)` and format
  normalization.
- `download` spawns yt-dlp with `format` set to chosen `formatId` (itag or selector) and `outtmpl` under the resolved
  target dir.
- Progress is mapped from yt-dlp hook and streamed via WS (no persistence). UI updates progress only from explicit "
  progress" messages.
- UI filters progressive (audio+video) formats; backend falls back to `<formatId>+bestaudio/best` when needed.

## 5) UI behavior

- Minimal single page (index.html) styled with Tailwind (CDN), with a light/dark theme toggle.
    - URL input
    - Button: "(Re) Load Video Info" -> calls /api/probe and fills quality dropdown
    - Quality dropdown populated from probe (only progressive formats with audio+video)
    - Target directory input:
        - Local run: editable, validated/sandboxed server-side
        - Docker: read-only, prefilled from `/health.hostDownloadsDir`; change by setting `DOWNLOADS_HOST_DIR` and
          restarting
    - Download button starts job and opens a WS connection; UI shows a visual progress bar and status messages; inputs
      aligned with consistent sizing.
    - After completion, UI shows the host path when available and provides a copy button.

## 6) Download flow

1) User enters URL -> Probe -> Choose format -> Provide targetDir -> Start
2) Service validates targetDir (exists/creatable, writable) and URL
3) Create in-memory job entry
4) Run yt-dlp with options:
    - `format`: chosen formatId (itag or format selector)
    - `merge_output_format`: mp4/mkv
    - `outtmpl`: built to include useful tokens; collisions get a numeric suffix to ensure uniqueness
    - `progress_hooks`: [progress_mapper]
    - Audio presence: if the selected format is video-only, automatically combine with bestaudio (e.g.,
      `<formatId>+bestaudio/best`) to ensure the final file has sound
5) Progress updates: push via WS (no storage)
6) On success: mark `succeeded`, return final file path and host path (in Docker)
7) On failure: mark `failed`, include error

## 7) Error handling and validation

- URL validation: basic scheme/host check; yt-dlp will perform deeper checks
- Directory validation: expanduser, resolve, must be under an allowed base (configurable)
- Disk space check (optional), permission errors captured with actionable messages
- Timeouts and graceful cancellation
- Robust mapping from yt-dlp progress to uniform events

## 8) Security considerations

- Do not execute arbitrary shell input; all yt-dlp args are constructed from validated inputs
- Restrict writable directories to a configurable whitelist or base path
- Avoid path traversal via normalization and checking realpath containment
- CORS: local development defaults; app serves static UI and APIs on same origin

## 9) Dependencies and installation

- System: ffmpeg must be installed and discoverable in PATH
- Python dependencies (managed via Poetry/pyproject.toml):
    - fastapi
    - uvicorn[standard]
    - yt-dlp
    - pydantic
    - pydantic-settings

    - websockets (via Starlette/FastAPI)
- Container: Dockerfile (python:3.11-slim + ffmpeg + Poetry) and docker-compose (bind-mount host downloads dir)

## 10) Development and run

- Logging configured once at app startup
- Local run: `poetry run uvicorn yt_downloader.main:app --reload`
- Docker run: `docker compose up --build` (mounts `${HOME}/Downloads/ytdl` by default)
- Configuration:
    - `DOWNLOADS_HOST_DIR` (container only): Host path bind-mounted to `/downloads`; surfaced by `/health` to prefill
      the UI target directory (read-only in Docker).
    - `YTD_CONCURRENT_FRAGMENTS` (default: 5): Number of fragments to download concurrently when supported.
- Default download directory: `~/Downloads/ytdl` locally; `/downloads` in container (host-mapped)

## 11) Milestones

- M1: Scaffold project, config, logging, health endpoint, static UI skeleton
- M2: Probe endpoint + UI integration (quality dropdown)
- M3: Download job orchestration with WS progress (no persistence)
- M4: UI polish with Tailwind (dark theme), aligned inputs, visual progress bar; progress semantics refined;
  validation/error messages, tests, docs
- M5: Dockerization with ffmpeg, host path mapping, UI host path display, read-only target dir in container

## 12) Acceptance criteria

- User can probe a YouTube URL and see available qualities without the YouTube API
- Local: user can select quality and an editable target directory; download succeeds under the allowed base
- Docker: target directory is read-only and reflects the mounted host directory; downloads land on the host
- Progress is visible, errors are actionable, and the final host-visible file path is shown
- No API keys required; ffmpeg is the only system dependency