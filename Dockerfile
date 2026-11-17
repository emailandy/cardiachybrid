# syntax=docker/dockerfile:1
# ==============================================================================
# Stage 1: Build the React 18 + Vite Control Center Frontend
# ==============================================================================
FROM node:22-slim AS ui-builder

WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm install --no-audit --no-fund

COPY ui/index.html ui/vite.config.js ./
COPY ui/src ./src
RUN npm run build

# ==============================================================================
# Stage 2: Cloud Run Service Runtime (Python 3.11 + FFmpeg + OpenCV + SoundFile)
# ==============================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GOOGLE_API_USE_CLIENT_CERTIFICATE=false \
    PORT=8080

WORKDIR /app

# Native runtime libraries required by ffmpeg/ffprobe, soundfile, and opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    libglib2.0-0 \
    libsndfile1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for layer caching
COPY pyproject.toml ./
COPY bq ./bq
COPY codegen ./codegen
COPY eval ./eval
COPY ingest ./ingest
COPY metrics ./metrics
COPY pipeline ./pipeline
COPY prompts ./prompts
COPY reducer ./reducer
COPY router ./router
COPY sensors ./sensors
COPY ui/*.py ./ui/

RUN pip install --no-cache-dir .

# Copy runtime schemas, registries, fixtures, saved live runs, and optional cached media
COPY . .
COPY --from=ui-builder /ui/dist ./ui/dist

# Deterministically compile REDCap + AI-CARES generated modules (safe even on fresh clones)
RUN python -m codegen.emit_python \
    && python -m codegen.emit_branching \
    && python -m codegen.emit_aicares

# Non-root runtime user with writable cache, upload, and live-job directories
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.video_cache/posters /app/.video_cache/uploads /app/results/live_runs /app/.resus_qc_tmp \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

CMD ["python", "ui/server.py"]
