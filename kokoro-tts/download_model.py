#!/usr/bin/env python3
"""
download_model.py — Bake Kokoro-82M weights into the Docker image at build time.

Run during `docker build` with no GPU available. The pipeline downloads the
model weights into HF_HOME (/app/hf_cache) on first initialisation.

At runtime the handler reloads the pipeline from the cached weights — no
re-download occurs.
"""
import os
import time

print("[download] Starting Kokoro-82M weight download...")
print(f"[download] HF_HOME={os.environ.get('HF_HOME', 'not set')}")

t0 = time.time()

from kokoro import KPipeline  # noqa: E402

print("[download] Initialising KPipeline (lang_code='a') to pull weights...")
pipeline = KPipeline(lang_code="a")

elapsed = time.time() - t0
cache_dir = os.environ.get("HF_HOME", "/app/hf_cache")
print(f"[download] Done in {elapsed:.1f}s — weights cached to {cache_dir}")

del pipeline
print("[download] Kokoro-82M model downloaded and baked into image.")
