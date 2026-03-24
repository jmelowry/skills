#!/usr/bin/env bash
# build_and_push.sh — Build and push the dia-tts image to GHCR.
# Run from within the dia-tts/ directory.
#
# Usage:
#   ./build_and_push.sh
#   IMAGE_TAG=sha-abc1234 ./build_and_push.sh
#   DOCKER_USER=yourname ./build_and_push.sh
set -euo pipefail

DOCKER_USER="${DOCKER_USER:-jmelowry}"
IMAGE_NAME="ghcr.io/${DOCKER_USER}/dia-tts"
IMAGE_TAG="${IMAGE_TAG:-latest}"
FULL_TAG="${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building ${FULL_TAG} (platform: linux/amd64)..."

# Fetch HF token via 1Password (never passed as a build-arg — injected as a BuildKit secret)
HF_TOKEN=$(op read "op://claude/hf-api/credential" 2>/dev/null || echo "")

if [[ -n "$HF_TOKEN" ]]; then
    DOCKER_BUILDKIT=1 docker build \
        --platform linux/amd64 \
        --secret id=hf_token,env=HF_TOKEN \
        -t "${FULL_TAG}" \
        .
else
    echo "Warning: hf-api token not found in 1Password — build may fail if Dia2-1B is gated."
    DOCKER_BUILDKIT=1 docker build \
        --platform linux/amd64 \
        -t "${FULL_TAG}" \
        .
fi

echo ""
echo "Pushing ${FULL_TAG}..."
docker push "${FULL_TAG}"

echo ""
echo "Done."
echo "  Image: ${FULL_TAG}"
echo "  Use this in your RunPod template: ${FULL_TAG}"
