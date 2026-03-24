#!/usr/bin/env python3
"""
download_model.py — Bake Dia2-1B weights into the Docker image at build time.

Run during `docker build` with no GPU available. The model is downloaded on CPU
with float32 so all weights land in HF_HOME (/app/hf_cache).

At runtime the handler reloads on CUDA with bfloat16 — the cached weights are
reused directly (no re-download).
"""
import os
import time

print("[download] Starting Dia2-1B weight download...")
print(f"[download] HF_HOME={os.environ.get('HF_HOME', 'not set')}")

t0 = time.time()

from dia2 import Dia2  # noqa: E402

print("[download] Calling Dia2.from_repo on CPU (no GPU at build time)...")
model = Dia2.from_repo("nari-labs/Dia2-1B", device="cpu", dtype="float32")

elapsed = time.time() - t0
cache_dir = os.environ.get("HF_HOME", "/app/hf_cache")
print(f"[download] Done in {elapsed:.1f}s — weights cached to {cache_dir}")

del model
print("[download] Weights baked into image. GPU + bfloat16 used at runtime.")
