# dia-tts — Dia2 TTS on RunPod Serverless

Deploys [Dia2-1B by Nari Labs](https://github.com/nari-labs/dia2) as a RunPod serverless worker.
Generates realistic multi-speaker dialogue audio from a text script.

## Prerequisites

- Docker with BuildKit enabled
- NVIDIA driver ≥ CUDA 12.8 (on the RunPod GPU)
- RunPod account with a serverless endpoint created
- 1Password CLI authenticated (`op whoami`)
- GitHub repo access for GHCR push

## Build and push

```bash
cd dia-tts
chmod +x build_and_push.sh
./build_and_push.sh
```

The script reads your HF token from 1Password automatically. The token is injected as a
BuildKit secret and never baked into any image layer.

To use a specific tag:
```bash
IMAGE_TAG=v1.0.0 ./build_and_push.sh
```

## Deploy on RunPod

1. Go to RunPod → Serverless → New Endpoint
2. Set the container image to: `ghcr.io/jmelowry/dia-tts:latest`
3. Select GPU: **RTX 4090** (24GB), **A4000** (16GB), or **L4** (24GB)
4. Set environment variable: `RUNPOD_INIT_TIMEOUT=300`
5. Set active workers to `0`, max workers to `3`
6. Copy the endpoint ID

Store the endpoint ID in 1Password:
```bash
op item create --vault claude --category "API Credential" \
  --title "runpod-dia-tts-endpoint" "credential[password]=<endpoint_id>"
```

## Test the endpoint

```bash
# Schema check only (no GPU needed)
python test_local.py --dry-run

# Generate a test clip (requires GPU + baked weights)
python test_local.py
open test_output.wav
```

Via the skill client:
```bash
python scripts/generate.py \
  --script "[S1] Hello! [S2] Hey, how are you? (laughs) [S1] Never better." \
  --out output.wav
```

## API example (curl)

```bash
ENDPOINT_ID=$(op read "op://claude/runpod-dia-tts-endpoint/credential")
API_KEY=$(op read "op://claude/runpod-api/credential")

# Submit job
JOB_ID=$(curl -s -X POST \
  "https://api.runpod.io/v2/${ENDPOINT_ID}/run" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "script": "[S1] Hello! [S2] Hey there. (laughs)",
      "seed": 42
    }
  }' | jq -r .id)

echo "Job: $JOB_ID"

# Poll for result
while true; do
  STATUS=$(curl -s \
    "https://api.runpod.io/v2/${ENDPOINT_ID}/status/${JOB_ID}" \
    -H "Authorization: Bearer ${API_KEY}")
  STATE=$(echo "$STATUS" | jq -r .status)
  echo "Status: $STATE"
  if [[ "$STATE" == "COMPLETED" ]]; then break; fi
  sleep 3
done

# Decode audio
echo "$STATUS" | jq -r '.output[-1].audio_b64' | base64 -d > output.wav
open output.wav
```

## Voice cloning

Pass 5–15s reference WAV files for each speaker:

```bash
# Encode reference WAVs as base64 in the job input
python scripts/generate.py \
  --script "[S1] Hi, I'm using voice cloning. [S2] Me too!" \
  --prefix-s1 my_voice.wav \
  --prefix-s2 other_voice.wav \
  --out cloned.wav
```

## Upgrading to Dia2-2B

The 2B model requires ~4GB VRAM (vs ~2GB for 1B). To switch:

1. Change `Dia2-1B` to `Dia2-2B` in `download_model.py` and `handler.py`
2. Rebuild the image (expect ~12GB compressed — consider network volume instead)
3. Recommended: move weights to a RunPod network volume at `/workspace/models/hf_cache`
   and set `HF_HOME=/workspace/models/hf_cache` in the RunPod template env

## Generation limit

Dia2 generates up to ~2 minutes of audio per call. For longer content, split the script
at natural break points and concatenate:

```bash
python scripts/generate.py --script "$PART1" --out part1.wav
python scripts/generate.py --script "$PART2" --out part2.wav
ffmpeg -i "concat:part1.wav|part2.wav" -acodec copy full.wav
```

## GitHub Secrets required

| Secret | Purpose |
|--------|---------|
| `HF_TOKEN` | HuggingFace token (for model download at build time) |
| `RUNPOD_API_KEY` | RunPod API key |
| `RUNPOD_DIA_TTS_TEMPLATE_ID` | RunPod template ID (for auto-deploy on push) |
