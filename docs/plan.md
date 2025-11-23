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
- Background execution: asyncio tasks with FastAPI BackgroundTasks; progress events via callbacks
- Realtime updates: WebSocket (FastAPI) for progress streaming
- Persistence: none (one-shot; no history/database)
- Config: pydantic-settings
- Logging: standard logging (JSON-friendly format), rotating file handler
- Tests: unittest
- Packaging: Poetry (pyproject.toml); optional Dockerfile later

## 3) System architecture
- Process model: single FastAPI process (Uvicorn). Jobs run in-process with cancellation and progress reporting.
- Modules
  - core/config.py – settings, directories, ffmpeg/yt-dlp detection
  - core/logging.py – logger init and formatters
  - domain/jobs.py – Job, JobStatus, ProgressEvent entities
  - services/probe.py – fetch available formats and metadata via yt-dlp (download=False)
  - services/downloader.py – orchestrate yt-dlp download with progress hook, error handling, cancellation
  - infra/fs.py – path validation, safe join, permission checks, ensure directories
  - infra/ytdlp_wrapper.py – yt-dlp options builder, progress mapping
  - api/http.py – REST endpoints (probe, start download, job status)
  - api/ws.py – WebSocket endpoint for live progress events
  - ui/ – static assets and template for the minimal web UI

### Directory layout
```
/ docs/plan.md
/ src/yt_downloader/__init__.py
/ src/yt_downloader/core/config.py
/ src/yt_downloader/core/logging.py
/ src/yt_downloader/domain/jobs.py
/ src/yt_downloader/services/probe.py
/ src/yt_downloader/services/downloader.py
/ src/yt_downloader/infra/fs.py
/ src/yt_downloader/infra/ytdlp_wrapper.py
/ src/yt_downloader/api/http.py
/ src/yt_downloader/api/ws.py
/ src/yt_downloader/ui/templates/index.html
/ src/yt_downloader/ui/static/app.js
/ src/yt_downloader/main.py
/ tests/ ...
/ pyproject.toml
/ poetry.lock
```

## 4) API design
- POST /api/probe
  - body: { url: string }
  - returns: { title, durationSec?, thumbnail?, formats: [{id, resolution, fps?, ext, vcodec, acodec, note}] }
- POST /api/download
  - body: { url: string, formatId: string, targetDir: string }
  - returns: { jobId }
- GET /api/jobs/{jobId}
  - returns: { status: "queued"|"running"|"succeeded"|"failed"|"cancelled", progressPercent, bytesDownloaded, filePath? , error? }
- POST /api/jobs/{jobId}/cancel
  - returns: { ok: true }
- WS /ws/jobs/{jobId}
  - server -> client progress events: { type: "progress"|"complete"|"error", progressPercent, speed?, eta?, message?, filePath? }

Notes
- `probe` is used to populate the quality dropdown. Use yt-dlp `extract_info(..., download=False)` and format normalization.
- `download` spawns yt-dlp with `format` set to chosen `formatId` (itag) and `outtmpl` pointing to `targetDir`.
- Progress is mapped from yt-dlp hook and streamed via WS (no persistence).
 - UI filters to progressive (audio+video) formats to avoid silent downloads; backend falls back to merging with bestaudio when needed.

## 5) UI behavior
- Minimal single page (index.html) styled with Tailwind (CDN), with a light/dark theme toggle.
  - URL input
  - Button: "Check" -> calls /api/probe and fills quality dropdown
  - Quality dropdown populated from probe (only progressive formats with audio+video)
  - Target directory input with a preset default (e.g., ~/Downloads/ytdl). For a full directory picker, future Electron/Tauri app is recommended; for the web UI we accept a validated server-side path string and/or a whitelist select.
  - Download button starts job and opens a WS connection; UI shows a visual progress bar and status messages; inputs aligned with consistent sizing.

## 6) Download flow
1) User enters URL -> Probe -> Choose format -> Provide targetDir -> Start
2) Service validates targetDir (exists/creatable, writable) and URL
3) Create in-memory job entry
4) Run yt-dlp with options:
   - `format`: chosen formatId (itag or format selector)
   - `merge_output_format`: mp4/mkv
   - `outtmpl`: computed from a base template including resolution/FPS tokens, e.g.: `%(title)s-%(id)s-%(height)sp-%(fps)sfps.%(ext)s`; missing tokens are removed; if the destination file exists, a numeric suffix like ` (1)` is appended to ensure uniqueness.
   - `progress_hooks`: [progress_mapper]
   - Audio presence: if the selected format is video-only, automatically combine with bestaudio (e.g., `<formatId>+bestaudio/best`) to ensure the final file has sound.
5) Progress updates: push via WS (no storage)
6) On success: mark `succeeded`, return final file path
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
- CORS limited to localhost by default

## 9) Dependencies and installation
- System: ffmpeg must be installed and discoverable in PATH
- Python dependencies (managed via Poetry/pyproject.toml):
  - fastapi
  - uvicorn[standard]
  - yt-dlp
  - pydantic
  - pydantic-settings

  - websockets (via Starlette/FastAPI)

## 10) Development and run
- Validate ffmpeg availability on startup; log helpful install hints
- Local run: `uvicorn yt_downloader.main:app --reload`
- Default download directory: `~/Downloads/ytdl` (override via env/config)

## 11) Milestones
- M1: Scaffold project, config, logging, health endpoint, static UI skeleton
- M2: Probe endpoint + UI integration (quality dropdown)
- M3: Download job orchestration with WS progress (no persistence)
 - M4: UI polish with Tailwind (light/dark themes), aligned inputs, visual progress bar; filenames include resolution/FPS with unique naming; validation/error messages, tests, packaging, docs
- Stretch: job queue abstraction, retry policy, multi-URL queue, playlist support, Electron/Tauri desktop wrapper

## 12) Acceptance criteria
- User can probe a YouTube URL and see available qualities without the YouTube API
- User can select quality and a local directory and download the video successfully
- Progress is visible, errors are actionable, and the final file path is shown
- No API keys required; ffmpeg is the only system dependency