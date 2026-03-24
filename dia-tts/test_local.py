#!/usr/bin/env python3
"""
test_local.py — Smoke test for the Dia2 RunPod handler.

Requires the model to be loaded (baked image or local HF cache).
Set HF_HOME to point at your local cache if running outside the container.

Usage:
    # Schema + import check only (no model, no GPU needed)
    python test_local.py --dry-run

    # Full generation test (requires GPU + baked weights)
    HF_HOME=/app/hf_cache python test_local.py
"""
import argparse
import base64
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Schema check only, no generation")
    parser.add_argument(
        "--script",
        default="[S1] Hello! [S2] Hey there, how are you? [S1] Doing great, thanks. (laughs)",
    )
    parser.add_argument("--out", default="test_output.wav")
    args = parser.parse_args()

    print("Checking schema import...")
    from schemas import JobInput, JobOutput  # noqa: F401

    inp = JobInput(script=args.script, seed=42)
    print(f"  script={inp.script[:50]}..., seed={inp.seed}")

    if args.dry_run:
        print("Dry run passed — schema OK.")
        return

    # Mock runpod.serverless.start so importing handler doesn't try to connect
    from unittest.mock import patch

    with patch("runpod.serverless.start"):
        from handler import handler

    job = {
        "id": "test-001",
        "input": {
            "script": args.script,
            "seed": 42,
            "cfg_scale": 2.0,
            "temperature": 0.8,
            "top_k": 50,
        },
    }

    print("Running handler (loading model on first call)...")
    results = []
    for r in handler(job):
        if "audio_b64" in r:
            print(f"  yield: {{audio_b64: <{len(r['audio_b64'])} chars>, ...}}")
        else:
            print(f"  yield: {r}")
        results.append(r)

    final = results[-1]
    if "error" in final:
        print(f"FAILED: {final['error']}")
        sys.exit(1)

    audio_bytes = base64.b64decode(final["audio_b64"])
    out_path = Path(args.out)
    out_path.write_bytes(audio_bytes)
    print(
        f"Passed. Audio written to {out_path} "
        f"({len(audio_bytes):,} bytes, {final['duration_seconds']}s @ {final['sample_rate']}Hz)"
    )


if __name__ == "__main__":
    main()
