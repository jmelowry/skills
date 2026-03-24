#!/usr/bin/env python3
"""
generate.py — Generate speech audio via the Kokoro RunPod endpoint.

Secrets are resolved from 1Password (claude vault) or environment variables.

Usage (single-speaker):
    python scripts/generate.py --text "Hello, world." --out output.mp3
    python scripts/generate.py --text "Hello." --voice am_michael --speed 1.1 --out output.wav

Usage (multi-speaker via segments file):
    python scripts/generate.py --segments-file segments.json --out output.mp3

    segments.json format:
    [
      {"text": "Hello there.", "voice": "af_heart", "speed": 1.0},
      {"text": "Hi back.", "voice": "am_michael", "speed": 1.0}
    ]

Required secrets (resolved automatically from 1Password):
    RUNPOD_API_KEY            → op://claude/runpod-api/credential
    RUNPOD_KOKORO_ENDPOINT    → op://claude/runpod-kokoro-tts-endpoint/credential

After deploying the RunPod worker, store the endpoint ID in 1Password:
    op item create --vault claude --category "API Credential" \\
      --title "runpod-kokoro-tts-endpoint" "credential[password]=<endpoint_id>"
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
    print(f"[kokoro-tts] Job submitted: {job_id}", file=sys.stderr)
    return job_id


def poll_job(endpoint_id: str, api_key: str, job_id: str) -> dict:
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            raise TimeoutError(f"Job {job_id} timed out after {POLL_TIMEOUT:.0f}s")

        result = _request(f"{RUNPOD_API_BASE}/{endpoint_id}/status/{job_id}", api_key)
        status = result.get("status", "UNKNOWN")
        print(f"[kokoro-tts] Status: {status} ({elapsed:.0f}s)", file=sys.stderr)

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
    parser = argparse.ArgumentParser(description="Generate speech audio via Kokoro RunPod endpoint")

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="Text to synthesise (single-speaker mode)")
    input_group.add_argument(
        "--segments-file",
        metavar="JSON",
        help="Path to JSON file with list of {text, voice, speed} for multi-speaker mode",
    )

    parser.add_argument("--voice", default="af_heart", help="Voice preset (single-speaker mode, default: af_heart)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech rate multiplier (0.5–2.0, default: 1.0)")
    parser.add_argument(
        "--lang-code", default="a",
        help="Language/accent code: 'a'=American English, 'b'=British English (default: a)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible output")
    parser.add_argument("--format", dest="output_format", choices=["mp3", "wav"], default="mp3", help="Output format (default: mp3)")
    parser.add_argument("--out", required=True, help="Output file path")
    args = parser.parse_args()

    api_key = resolve_secret("RUNPOD_API_KEY", "op://claude/runpod-api/credential")
    endpoint_id = resolve_secret("RUNPOD_KOKORO_ENDPOINT", "op://claude/runpod-kokoro-tts-endpoint/credential")

    job_input: dict = {"output_format": args.output_format}

    if args.segments_file:
        segments_path = Path(args.segments_file)
        if not segments_path.exists():
            print(f"Error: segments file not found: {segments_path}", file=sys.stderr)
            sys.exit(1)
        job_input["segments"] = json.loads(segments_path.read_text())
    else:
        job_input["text"] = args.text
        job_input["voice"] = args.voice
        job_input["speed"] = args.speed
        job_input["lang_code"] = args.lang_code

    if args.seed is not None:
        job_input["seed"] = args.seed

    job_id = submit_job(endpoint_id, api_key, job_input)
    output = poll_job(endpoint_id, api_key, job_id)

    if "error" in output:
        print(f"[kokoro-tts] Error: {output['error']}", file=sys.stderr)
        if "detail" in output:
            print(f"  Detail: {output['detail']}", file=sys.stderr)
        sys.exit(1)

    audio_b64 = output.get("audio_b64")
    if not audio_b64:
        print(f"[kokoro-tts] Error: no audio_b64 in output: {output}", file=sys.stderr)
        sys.exit(1)

    audio_bytes = base64.b64decode(audio_b64)
    out_path = Path(args.out)
    out_path.write_bytes(audio_bytes)

    duration = output.get("duration_seconds", "?")
    sample_rate = output.get("sample_rate", 24000)
    fmt = output.get("output_format", args.output_format)
    print(
        f"[kokoro-tts] Done. {out_path} ({duration}s, {sample_rate}Hz, {fmt}, {len(audio_bytes):,} bytes)",
        file=sys.stderr,
    )
    # Print the output path to stdout so callers can capture it
    print(str(out_path))


if __name__ == "__main__":
    main()
