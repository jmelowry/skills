FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    ffmpeg libsndfile1 espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HOME=/app/hf_cache \
    TRANSFORMERS_CACHE=/app/hf_cache \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN ln -sf /usr/bin/python3 /usr/bin/python

# ── PyTorch — isolated layer (rarely changes, ~2.5 GB) ────────────────────────
# hadolint ignore=DL3013,DL3059
RUN pip install --no-cache-dir \
    torch torchaudio \
    --index-url https://download.pytorch.org/whl/cu128

# ── Additional dependencies ───────────────────────────────────────────────────
COPY requirements.txt .
# hadolint ignore=DL3013,DL3059
RUN pip install --no-cache-dir -r requirements.txt

# Verify the import works before the expensive model download.
# hadolint ignore=DL3059
RUN python3 -c "from kokoro import KPipeline; print('[verify] kokoro import OK')"

# ── Bake model weights at build time (~340 MB, isolated layer) ────────────────
# HF_TOKEN is injected as a BuildKit secret and never appears in any image layer.
# Kokoro-82M is public (Apache 2.0) — token is accepted but not required.
COPY download_model.py .
RUN --mount=type=secret,id=hf_token,required=false \
    HF_TOKEN=$(cat /run/secrets/hf_token 2>/dev/null || echo "") \
    python3 download_model.py

# ── Worker source (last layer — most frequently changed) ──────────────────────
COPY handler.py schemas.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

CMD ["/app/entrypoint.sh"]
