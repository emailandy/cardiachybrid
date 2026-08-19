FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for opencv, etc.)
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application source code
COPY . .

# Set the default command for the pipeline
# Modify this if there is a specific entrypoint script, e.g., run_pipeline.py
CMD ["python", "-m", "scripts.build"]
