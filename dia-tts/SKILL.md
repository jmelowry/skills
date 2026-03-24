---
name: dia-tts
description: >
  Generate realistic multi-speaker dialogue audio using the Dia2 TTS model hosted on a RunPod
  serverless endpoint. Supports [S1]/[S2] speaker tags, nonverbal cues like (laughs) and (sighs),
  seeded generation for reproducibility, and voice cloning via reference WAV files. Use when the
  user asks to generate audio, synthesize speech, create a dialogue recording, make a podcast
  clip, or produce any spoken audio from a script. Also use when another skill needs a TTS
  primitive — call scripts/generate.py directly. Trigger on phrases like "generate audio of this",
  "synthesize this dialogue", "TTS this script", "make this into audio", "render this as speech",
  or "create a voice clip of this conversation".
compatibility:
  tools: [bash]
  python_deps: []  # stdlib only (urllib, base64, json, subprocess)
  secrets:
    - RUNPOD_API_KEY          # op://claude/runpod-api/credential
    - RUNPOD_DIA_ENDPOINT     # op://claude/runpod-dia-tts-endpoint/credential
---

# dia-tts Skill

Generates realistic dialogue audio from a script using **Dia2-1B by Nari Labs**, deployed as a
RunPod serverless endpoint. This is a **primitive** — other skills call it via `scripts/generate.py`
to get TTS audio without reimplementing the RunPod API client.

---

## What Dia2 produces

- Multi-speaker dialogue with `[S1]` / `[S2]` speaker tags
- Nonverbal cues: `(laughs)`, `(sighs)`, `(coughs)`, `(gasps)`, `(screams)`, `(whispers)`
- Output: 44.1 kHz mono WAV
- Max ~2 minutes per call
- Voice cloning via reference WAVs (5–15s each)

---

## Workflow

```
user request
    │
    ├─ resolve secrets (1Password → env)
    ├─ build job_input JSON
    ├─ POST /v2/{endpoint_id}/run  → job_id
    ├─ poll /v2/{endpoint_id}/status/{job_id} every 3s
    └─ decode audio_b64 → write WAV → done
```

---

## Step 1 — Resolve secrets

Secrets are pulled from 1Password automatically if `op` is authenticated:

| Secret | 1Password reference |
|--------|---------------------|
| `RUNPOD_API_KEY` | `op://claude/runpod-api/credential` |
| `RUNPOD_DIA_ENDPOINT` | `op://claude/runpod-dia-tts-endpoint/credential` |

**After deploying the RunPod worker**, store the endpoint ID once:
```bash
op item create --vault claude --category "API Credential" \
  --title "runpod-dia-tts-endpoint" "credential[password]=<endpoint_id>"
```

---

## Step 2 — Run the generator

### Direct invocation

```bash
python scripts/generate.py \
  --script "[S1] Hello there! [S2] Hey, how's it going? (laughs)" \
  --out output.wav
```

Full options:
```bash
python scripts/generate.py \
  --script "[S1] ... [S2] ..." \
  --out output.wav \
  --seed 42                    # reproducible output
  --cfg-scale 2.0              # classifier-free guidance (0.5–10.0)
  --temperature 0.8            # sampling temperature
  --top-k 50                   # top-k sampling
  --prefix-s1 speaker1.wav    # voice cloning reference for S1 (5–15s)
  --prefix-s2 speaker2.wav    # voice cloning reference for S2 (5–15s)
```

The script prints the output path to stdout and progress to stderr.

### As a primitive from another skill

```bash
# Capture the output path
AUDIO_PATH=$(python /path/to/dia-tts/scripts/generate.py \
  --script "$SCRIPT" \
  --out /tmp/dialogue.wav 2>/dev/null)
```

Or in Python (from a skill script):
```python
import subprocess, sys

result = subprocess.run(
    [sys.executable, "path/to/dia-tts/scripts/generate.py",
     "--script", script_text,
     "--out", str(output_path)],
    capture_output=True, text=True,
)
if result.returncode != 0:
    raise RuntimeError(f"dia-tts failed: {result.stderr}")
audio_path = result.stdout.strip()
```

---

## Script format

```
[S1] This is speaker one talking.
[S2] And this is speaker two responding. (laughs)
[S1] The model handles turn-taking naturally.
[S2] Including (sighs) nonverbal cues mid-sentence.
```

- Always start with a speaker tag
- Max ~2 minutes of audio per call (~600–800 words)
- For longer content, split into chunks and concatenate the WAV files with `ffmpeg`

---

## Chunking for long content

For scripts longer than ~2 minutes, split at natural boundaries and concatenate:

```bash
# Generate chunks
python scripts/generate.py --script "$CHUNK1" --out chunk1.wav
python scripts/generate.py --script "$CHUNK2" --out chunk2.wav

# Concatenate
ffmpeg -i "concat:chunk1.wav|chunk2.wav" -acodec copy output.wav
```

---

## RunPod endpoint settings (reference)

After deployment, configure the endpoint in the RunPod console:

| Setting | Value |
|---------|-------|
| GPU | RTX 4090 (24GB), A4000 (16GB), or L4 (24GB) |
| Active workers | 0 (pure serverless) |
| Max workers | 3 |
| `RUNPOD_INIT_TIMEOUT` | 300 (cold start can take 30–60s) |

---

## Error handling

| Error | Action |
|-------|--------|
| `RUNPOD_DIA_ENDPOINT` not set | Prompt user to deploy worker and run the `op item create` command above |
| `RUNPOD_API_KEY` not set | Check `op://claude/runpod-api/credential` exists |
| `{"error": "oom"}` from endpoint | Script or voice prefix too long; reduce script length or use a GPU with more VRAM |
| Job status `FAILED` | Check RunPod logs; common causes: CUDA version mismatch, model cache corruption |
| Poll timeout (300s) | Endpoint may be cold-starting; retry or increase `POLL_TIMEOUT` in `scripts/generate.py` |

---

## Output

`scripts/generate.py` writes a WAV file and prints its path to stdout:

```
output.wav
```

Progress and status go to stderr:
```
[dia-tts] Job submitted: abc123
[dia-tts] Status: IN_QUEUE (0s)
[dia-tts] Status: IN_PROGRESS (3s)
[dia-tts] Status: COMPLETED (21s)
[dia-tts] Done. output.wav (18.4s, 44100Hz, 1,626,044 bytes)
```
