#!/usr/bin/env python3
"""
download_model.py — Bake Kokoro-82M weights into the Docker image at build time.

Run during `docker build` with no GPU available. Downloads the base model AND
all voice .pt files so the worker never hits HuggingFace Hub at runtime.

At runtime the handler reloads everything from the local cache.
"""
import os
import time

print("[download] Starting Kokoro-82M weight download...")
print(f"[download] HF_HOME={os.environ.get('HF_HOME', 'not set')}")

t0 = time.time()

from kokoro import KPipeline  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

# Initialise the base pipeline for both language codes — downloads model weights.
print("[download] Loading base model for lang_code='a' (American)...")
pipeline_a = KPipeline(lang_code="a")
print("[download] Loading base model for lang_code='b' (British)...")
pipeline_b = KPipeline(lang_code="b")
del pipeline_a, pipeline_b

# All voices used by the handler — explicitly download each voice .pt file so
# they land in HF_HOME and are never fetched at inference time on RunPod.
VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael",
    "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis",
]

REPO_ID = "hexgrad/Kokoro-82M"

print(f"[download] Pre-fetching {len(VOICES)} voice files from {REPO_ID}...")
for voice in VOICES:
    path = hf_hub_download(repo_id=REPO_ID, filename=f"voices/{voice}.pt")
    print(f"[download]   {voice}.pt → {path}")

elapsed = time.time() - t0
cache_dir = os.environ.get("HF_HOME", "/app/hf_cache")
print(f"[download] Done in {elapsed:.1f}s — all weights and voices cached to {cache_dir}")
print("[download] Kokoro-82M model + all voices baked into image.")
