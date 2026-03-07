# RunPod Serverless Worker for ACE-Step 1.5 Music Generation
# Multi-stage build: download models → build runtime → slim worker image
#
# Build (no HF token needed — model is public):
#   docker build -t acestep-serverless:latest .
#
# Test locally:
#   docker run --gpus all -p 8080:8080 acestep-serverless:latest

# ─── Stage 1: Download models from HuggingFace ───
FROM python:3.11-slim AS model-downloader

RUN pip install --no-cache-dir huggingface_hub

# ACE-Step 1.5 model is public — no token required
COPY download_model.py /tmp/download_model.py
RUN python /tmp/download_model.py

# ─── Stage 2: Runtime with ACE-Step + RunPod SDK ───
FROM nvidia/cuda:12.6.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip \
    git curl ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install uv for fast dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Clone ACE-Step 1.5
RUN git clone --depth 1 https://github.com/ACE-Step/ACE-Step-1.5.git /app/acestep-repo

WORKDIR /app/acestep-repo

# Install ACE-Step dependencies + RunPod SDK
RUN uv sync && \
    uv add --no-sync runpod requests && \
    uv sync

# Copy models from stage 1
COPY --from=model-downloader /models/acestep-v15-base /app/checkpoints/acestep-v15-base

# Symlink for ACE-Step to find models
RUN mkdir -p /app/acestep-repo/checkpoints && \
    ln -sf /app/checkpoints/acestep-v15-base /app/acestep-repo/checkpoints/acestep-v15-base

# ACE-Step environment config
ENV ACESTEP_DEVICE=cuda \
    ACESTEP_API_HOST=0.0.0.0 \
    ACESTEP_API_PORT=8000 \
    ACESTEP_OUTPUT_DIR=/tmp/acestep-output

RUN mkdir -p /tmp/acestep-output

# Copy our RunPod handler
COPY handler.py /app/acestep-repo/handler.py

# RunPod serverless expects to listen on 8080 (handled by runpod SDK)
EXPOSE 8080

# Verify runpod is importable at build time
RUN uv run python -c "import runpod; print(f'runpod {runpod.__version__} OK')"

CMD [".venv/bin/python", "handler.py"]
