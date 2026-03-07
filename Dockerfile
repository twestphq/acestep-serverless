# RunPod Serverless Worker for ACE-Step 1.5 Music Generation
# Uses pre-built base image with models + deps. Handler-only rebuild (~1 min).
#
# Prerequisites: build and push base image first (one-time):
#   docker build -f Dockerfile.base -t twestphq/acestep-base:latest .
#   docker push twestphq/acestep-base:latest
#
# Build:
#   docker build -t acestep-serverless:latest .
#
# Test locally:
#   docker run --gpus all -p 8080:8080 acestep-serverless:latest

FROM ghcr.io/twestphq/acestep-base:latest

WORKDIR /app/acestep-repo

# Copy our RunPod handler (only thing that changes between deploys)
COPY handler.py /app/acestep-repo/handler.py

EXPOSE 8080

CMD [".venv/bin/python", "handler.py"]
