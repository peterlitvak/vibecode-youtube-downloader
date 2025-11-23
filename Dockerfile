# syntax=docker/dockerfile:1
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System dependencies (ffmpeg for merging/processing media)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Poetry for dependency management (no virtualenv inside container)
RUN pip install --no-cache-dir poetry

WORKDIR /app

# Copy dependency metadata first for better layer caching
COPY pyproject.toml poetry.lock* /app/

# Install only application dependencies (not the project itself)
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# Copy source
COPY src /app/src

# Ensure the app imports from source path
ENV PYTHONPATH="/app/src:${PYTHONPATH}"

# Default directories (can be overridden at runtime)
ENV YTD_ALLOWED_BASE_DIR="/downloads"
ENV YTD_DEFAULT_DOWNLOAD_DIR="/downloads"

# Create default download directory
RUN mkdir -p /downloads

EXPOSE 8000

# Start FastAPI app
CMD ["poetry", "run", "uvicorn", "yt_downloader.main:app", "--host", "0.0.0.0", "--port", "8000"]
