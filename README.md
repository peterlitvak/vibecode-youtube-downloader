# YouTube Downloader

FastAPI-based service with a minimal web UI for one‑shot YouTube downloads via yt‑dlp. Streams progress over WebSocket,
saves to a configurable downloads directory, and ships with a ready‑to‑use Docker setup.

---

## Run in Docker (recommended)

Prerequisites:

- Docker and Docker Compose

Quick start (writes downloads to `~/Downloads/ytdl` on your host):

```bash
docker compose up --build
```

Open the UI at:

- http://localhost:8000

Downloads directory mapping:

- Inside the container, files are written to `/downloads`.
- By default, this is bind-mounted to `${HOME}/Downloads/ytdl` on your host.

Override the host downloads directory:

```bash
DOWNLOADS_HOST_DIR="/absolute/host/path" docker compose up --build
```

Environment variables (already set sensibly in `docker-compose.yml`):

- `DOWNLOADS_HOST_DIR` (container only; default: `${HOME}/Downloads/ytdl`)
    - Host path bind‑mounted into the container at `/downloads`.
- `YTD_CONCURRENT_FRAGMENTS` (default: `5`)
    - Number of fragments to download concurrently for segmented streams (HLS/DASH).

      Notes:
        - Final downloaded files live on the host (volume mount). The container’s writable layer won’t grow with
          downloads.
        - If you change the container target path, adjust the volume and `DOWNLOADS_HOST_DIR` accordingly.
        - In Docker, the Target directory field in the UI is read-only. To change where files go, set
          `DOWNLOADS_HOST_DIR` in `docker-compose.yml` (or via env on startup) and restart the service.

---

## Run locally (without Docker)

Prerequisites:

- Python 3.11
- Poetry
- ffmpeg (must be installed on your system and available on PATH)

Poetry installs `yt-dlp` with its packaged Deno/EJS JavaScript runtime support, so no separate Node or Deno install is
required for normal local use.

Install Poetry (pick one):

- macOS (Homebrew):

```bash
brew install poetry
```

- macOS/Linux (pipx):

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install poetry
```

- Windows (winget or choco):

```powershell
winget install Python.Pipx
pipx install poetry
# or: choco install poetry
```

Install ffmpeg:

- macOS (Homebrew):

```bash
brew install ffmpeg
```

- Ubuntu/Debian:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

- Fedora:

```bash
sudo dnf install -y ffmpeg
```

- Arch:

```bash
sudo pacman -S ffmpeg
```

- Windows:

```powershell
winget install Gyan.FFmpeg
# or: choco install ffmpeg --installargs "/NoPath"
# Ensure ffmpeg is added to PATH after install
```

Verify tools are on PATH:

```bash
poetry --version
ffmpeg -version
```

Install dependencies:

```bash
poetry install
```

If you have multiple Python versions installed and want to force Python 3.11 for this project:

```bash
poetry env use 3.11
poetry install
```

Activate the virtual environment:

```bash
# Option A (Poetry 2.x+): activate without leaving your current shell (macOS/Linux; bash/zsh)
eval $(poetry env activate)

# Option B: manually activate it (macOS/Linux)
source "$(poetry env info --path)/bin/activate"
```

Note: On macOS, `python` might not be available outside the virtual environment. Use `python3` instead.

On Windows (PowerShell):

```powershell
Invoke-Expression (poetry env activate)

# Alternatively, manual activation
& "$(poetry env info --path)\\Scripts\\Activate.ps1"
```

If you prefer `poetry shell`, install the Poetry shell plugin:

```bash
poetry self add poetry-plugin-shell
poetry shell
```

(Optional) Configure environment via `.env` in the project root:

```env
# .env (example)
# Concurrency for segmented streams (HLS/DASH)
YTD_CONCURRENT_FRAGMENTS="5"
```

Start the server:

```bash
# Option A: without activating the venv
poetry run uvicorn yt_downloader.main:app --host 0.0.0.0 --port 8000 --reload

# Option B: after activating the venv
uvicorn yt_downloader.main:app --host 0.0.0.0 --port 8000 --reload

# Option C: python -m (spawns uvicorn)
poetry run python -m yt_downloader.main
```

Open:

- http://127.0.0.1:8000

---

## Using the app

1. Paste a YouTube URL and click "Check" to probe available formats.
2. Choose a progressive (audio+video) quality.
3. Optionally set a target directory. Locally, this field is editable and must be under the allowed base directory. In
   Docker, it is read-only and reflects the mounted host directory. The UI pre-fills this field from `/health` (
   hostDownloadsDir or defaultDownloadDir).
4. Click "Download". A WebSocket will stream progress. When complete, the UI shows the saved file path.
    - In Docker, the UI displays the host path (e.g., `~/Downloads/ytdl/...`) for convenience.

---

## API overview

- `POST /api/probe` → Probe formats
- `POST /api/download` → Start a download job (returns `jobId`)
- `GET /api/jobs/{jobId}` → Poll job snapshot
- `WS /ws/jobs/{jobId}` → Real-time progress
- `GET /health` → Health check
- `GET /` → Static HTML UI

---

## Testing

Integration tests (require internet access for the probe call):

```bash
poetry run python -m unittest -v
```

---

## Architecture

- Backend: FastAPI + Uvicorn, Pydantic Settings
- Downloader: yt‑dlp + packaged Deno/EJS JavaScript runtime support + ffmpeg
- Progress: WebSocket fan-out from an in‑memory job manager
- UI: Single static HTML + JS (Tailwind via CDN)
- Container: Python 3.11 slim, ffmpeg installed, Poetry-managed dependencies

Notes & constraints:

- Jobs are in-memory and ephemeral (no persistence across restarts).
- All target directories are sandboxed under an allowed base directory
  (locally under `~/Downloads`, in Docker under `/downloads`).
- YouTube extractor compatibility depends on keeping `yt-dlp` current; the lockfile pins the tested version.
