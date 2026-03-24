#!/usr/bin/env python3
"""
generate.py — Generate dialogue audio via the Dia2 RunPod endpoint.

Secrets are resolved from 1Password (claude vault) or environment variables.

Usage:
    python scripts/generate.py --script "[S1] Hello. [S2] Hey there." --out output.wav
    python scripts/generate.py --script "..." --seed 42 --out output.wav
    python scripts/generate.py --script "..." --prefix-s1 ref_s1.wav --prefix-s2 ref_s2.wav --out output.wav

Required secrets (resolved automatically from 1Password):
    RUNPOD_API_KEY       → op://claude/runpod-api/credential
    RUNPOD_DIA_ENDPOINT  → op://claude/runpod-dia-tts-endpoint/credential

After deploying the RunPod worker, store the endpoint ID in 1Password:
    op item create --vault claude --category "API Credential" \\
      --title "runpod-dia-tts-endpoint" "credential[password]=<endpoint_id>"
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

RUNPOD_API_BASE = "https://api.runpod.io/v2"
POLL_INTERVAL = 3.0
POLL_TIMEOUT = 300.0


def resolve_secret(env_key: str, op_ref: str) -> str:
    val = os.environ.get(env_key)
    if val:
        return val
    try:
        result = subprocess.run(
            ["op", "read", op_ref],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        print(f"Error: {env_key} not set and 'op' CLI not found.", file=sys.stderr)
        print(f"  Set {env_key}=... or install/authenticate the 1Password CLI.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: could not read {op_ref} from 1Password: {e.stderr.strip()}", file=sys.stderr)
        print("  Ensure 'op' is authenticated and the item exists in the claude vault.", file=sys.stderr)
        sys.exit(1)


def _request(url: str, api_key: str, method: str = "GET", body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} from RunPod: {body_text}") from e


def submit_job(endpoint_id: str, api_key: str, job_input: dict) -> str:
    result = _request(
        f"{RUNPOD_API_BASE}/{endpoint_id}/run",
        api_key, method="POST", body={"input": job_input},
    )
    job_id = result.get("id")
    if not job_id:
        raise RuntimeError(f"No job ID in RunPod response: {result}")
    print(f"[dia-tts] Job submitted: {job_id}", file=sys.stderr)
    return job_id


def poll_job(endpoint_id: str, api_key: str, job_id: str) -> dict:
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            raise TimeoutError(f"Job {job_id} timed out after {POLL_TIMEOUT:.0f}s")

        result = _request(f"{RUNPOD_API_BASE}/{endpoint_id}/status/{job_id}", api_key)
        status = result.get("status", "UNKNOWN")
        print(f"[dia-tts] Status: {status} ({elapsed:.0f}s)", file=sys.stderr)

        if status == "COMPLETED":
            output = result.get("output")
            # return_aggregate_stream: True produces a list; take the last item
            if isinstance(output, list):
                output = output[-1] if output else {}
            return output or {}

        if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError(
                f"Job {job_id} ended with status {status}: {result.get('error', '')}"
            )

        time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dialogue audio via Dia2 RunPod endpoint")
    parser.add_argument("--script", required=True, help="Dialogue script with [S1]/[S2] tags")
    parser.add_argument("--out", required=True, help="Output WAV file path")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible output")
    parser.add_argument("--cfg-scale", type=float, default=2.0)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument(
        "--prefix-s1",
        metavar="WAV",
        help="Path to S1 speaker reference WAV for voice cloning (5–15s)",
    )
    parser.add_argument(
        "--prefix-s2",
        metavar="WAV",
        help="Path to S2 speaker reference WAV for voice cloning (5–15s)",
    )
    args = parser.parse_args()

    api_key = resolve_secret("RUNPOD_API_KEY", "op://claude/runpod-api/credential")
    endpoint_id = resolve_secret("RUNPOD_DIA_ENDPOINT", "op://claude/runpod-dia-tts-endpoint/credential")

    job_input: dict = {
        "script": args.script,
        "cfg_scale": args.cfg_scale,
        "temperature": args.temperature,
        "top_k": args.top_k,
    }
    if args.seed is not None:
        job_input["seed"] = args.seed
    if args.prefix_s1:
        job_input["prefix_s1_b64"] = base64.b64encode(Path(args.prefix_s1).read_bytes()).decode()
    if args.prefix_s2:
        job_input["prefix_s2_b64"] = base64.b64encode(Path(args.prefix_s2).read_bytes()).decode()

    job_id = submit_job(endpoint_id, api_key, job_input)
    output = poll_job(endpoint_id, api_key, job_id)

    if "error" in output:
        print(f"[dia-tts] Error: {output['error']}", file=sys.stderr)
        if "detail" in output:
            print(f"  Detail: {output['detail']}", file=sys.stderr)
        sys.exit(1)

    audio_b64 = output.get("audio_b64")
    if not audio_b64:
        print(f"[dia-tts] Error: no audio_b64 in output: {output}", file=sys.stderr)
        sys.exit(1)

    audio_bytes = base64.b64decode(audio_b64)
    out_path = Path(args.out)
    out_path.write_bytes(audio_bytes)

    duration = output.get("duration_seconds", "?")
    sample_rate = output.get("sample_rate", 44100)
    print(
        f"[dia-tts] Done. {out_path} ({duration}s, {sample_rate}Hz, {len(audio_bytes):,} bytes)",
        file=sys.stderr,
    )
    # Print the output path to stdout so callers can capture it
    print(str(out_path))


if __name__ == "__main__":
    main()
