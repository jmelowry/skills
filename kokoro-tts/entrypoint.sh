#!/usr/bin/env bash
set -euo pipefail

# Model weights are baked into the image — no download needed at start.
# Lock HF to offline mode to prevent accidental network calls during inference.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

exec python3 -u /app/handler.py
