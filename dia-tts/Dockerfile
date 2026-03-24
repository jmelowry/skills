FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    git ffmpeg libsndfile1 \
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

# ── dia2 ──────────────────────────────────────────────────────────────────────
# pip install (git URL or local path) produces an empty UNKNOWN-0.0.0 wheel
# because pip's build isolation can't resolve torch>=2.8.0 (not on PyPI).
# dia2 is pure Python — copy the package directory directly to site-packages.
# Separate layer from PyTorch so the ~2.5 GB torch layer stays cached on rebuilds.
# hadolint ignore=DL3059
RUN git clone --depth=1 https://github.com/nari-labs/dia2.git /tmp/dia2-src \
    && cp -r /tmp/dia2-src/dia2 \
         "$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')/dia2" \
    && rm -rf /tmp/dia2-src

# Verify the import works before the expensive model download.
RUN python3 -c "from dia2 import Dia2; print('[verify] dia2 import OK')"

# ── Additional dependencies ───────────────────────────────────────────────────
COPY requirements.txt .
# hadolint ignore=DL3013,DL3059
RUN pip install --no-cache-dir -r requirements.txt

# ── Bake model weights at build time (~2 GB, isolated layer) ──────────────────
# HF_TOKEN is injected as a BuildKit secret and never appears in any image layer.
COPY download_model.py .
RUN --mount=type=secret,id=hf_token,required=false \
    HF_TOKEN=$(cat /run/secrets/hf_token 2>/dev/null || echo "") \
    python3 download_model.py

# ── Worker source (last layer — most frequently changed) ──────────────────────
COPY handler.py schemas.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

CMD ["/app/entrypoint.sh"]
