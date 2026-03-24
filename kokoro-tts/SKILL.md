---
name: kokoro-tts
description: >
  Generate high-quality speech audio using Kokoro-82M, a fast open-source
  TTS model with 20+ voice presets for American and British English. Supports
  single-speaker and multi-speaker synthesis via a RunPod serverless worker.
tools: Bash
---

# kokoro-tts

Kokoro-82M is a lightweight (~82M parameter) open-source TTS model from
hexgrad (Apache 2.0). It produces natural-sounding 24kHz audio with 20+ voice
presets covering American and British English accents. Inference is fast —
suitable for long-form narration and multi-speaker scenes.

## When to use Kokoro vs dia-tts

| Use case | Recommended |
|---|---|
| Long-form narration, audiobooks, voiceovers | **kokoro-tts** |
| Multi-speaker scenes with different voices | **kokoro-tts** |
| Naturalistic two-person dialogue (S1/S2) | **dia-tts** |
| Voice cloning from a reference audio clip | **dia-tts** |

## Available voices

**American English** (`lang_code: "a"`):
- `af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `af_sky` — American female
- `am_adam`, `am_michael` — American male

**British English** (`lang_code: "b"`):
- `bf_emma`, `bf_isabella` — British female
- `bm_george`, `bm_lewis` — British male

## Schema

### Single-speaker mode

```json
{
  "text": "Hello, world. This is Kokoro speaking.",
  "voice": "af_heart",
  "speed": 1.0,
  "lang_code": "a",
  "seed": 42,
  "output_format": "mp3"
}
```

### Multi-speaker mode

Provide `segments` instead of (or without) `text`. Each segment can use a
different voice and speed. The audio arrays are concatenated in order.

```json
{
  "segments": [
    {"text": "Welcome to the show.", "voice": "af_heart", "speed": 1.0},
    {"text": "Thanks for having me.", "voice": "am_michael", "speed": 0.95},
    {"text": "Let's get started.", "voice": "af_heart", "speed": 1.0}
  ],
  "output_format": "mp3"
}
```

### Response

```json
{
  "audio_b64": "<base64-encoded audio>",
  "sample_rate": 24000,
  "duration_seconds": 4.2,
  "output_format": "mp3"
}
```

## CLI usage via scripts/generate.py

Secrets are resolved automatically from 1Password (claude vault) or
environment variables (`RUNPOD_API_KEY`, `RUNPOD_KOKORO_ENDPOINT`).

```bash
# Single-speaker — American female, default voice
python scripts/generate.py \
  --text "Hello, world." \
  --out hello.mp3

# Single-speaker — British male, WAV output
python scripts/generate.py \
  --text "Good morning from London." \
  --voice bm_george \
  --lang-code b \
  --format wav \
  --out morning.wav

# Single-speaker — with seed for reproducibility
python scripts/generate.py \
  --text "Reproducible speech." \
  --voice af_bella \
  --seed 42 \
  --out speech.mp3

# Multi-speaker — from a segments JSON file
python scripts/generate.py \
  --segments-file segments.json \
  --out dialogue.mp3
```

### segments.json example

```json
[
  {"text": "Welcome to today's briefing.", "voice": "af_heart", "speed": 1.0},
  {"text": "Here are the key points.", "voice": "am_adam", "speed": 1.0},
  {"text": "First, revenue is up 12%.", "voice": "af_heart", "speed": 1.0}
]
```

## Secrets required

Store these in 1Password (claude vault) before using:

```bash
# RunPod API key (shared across workers)
op item create --vault claude --category "API Credential" \
  --title "runpod-api" "credential[password]=<your_runpod_api_key>"

# Kokoro endpoint ID (get from RunPod console after deploying)
op item create --vault claude --category "API Credential" \
  --title "runpod-kokoro-tts-endpoint" "credential[password]=<endpoint_id>"
```
