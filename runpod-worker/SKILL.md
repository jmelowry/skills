---
name: runpod-worker
description: Build, containerize, and deploy a RunPod serverless worker — handler scaffolding, model loading, streaming responses, network volume patterns, Dockerfile layer optimization, GitHub Actions CI/CD to GHCR with linting, and automated RunPod template management via GraphQL API. Covers image (SDXL/FLUX/RealVisXL), TTS, and text generation workers.
---

This skill produces a production-ready RunPod serverless worker. It covers all three worker types with shared architectural patterns and generates the complete file set: handler, pipelines, volume paths, storage, entrypoint, download scripts, Dockerfile, tests, and GitHub Actions CI/CD workflow.

The user provides: worker name, type, model(s), and any special requirements. Claude produces the full implementation.

---

## Step 1 — Gather Context

Before generating anything, collect:

1. **Worker name** — slug used for directory name, image name, and RunPod template (e.g. `portrait-xl`)
2. **Worker type** — `image`, `tts`, or `text`
3. **Model(s)** — specific checkpoints, LoRAs, voice models, or LLMs
4. **Network volume path** — where the volume is mounted (default: `/workspace/models` via `VOLUME_ROOT` env var)
5. **Job input/output schema** — what fields the caller sends and receives
6. **Internal packages** — any shared packages in this repo that the worker needs (note their path)
7. **Special requirements** — LoRA loading, multi-model switching, face ID, batching, streaming, etc.

If worker type is `image`, also collect:
- Base model family (FLUX, SDXL, SD1.5, RealVisXL)
- LoRA support needed?
- IP-Adapter / ControlNet / InstantID?
- Output destination (R2 bucket / CDN base URL)

If worker type is `tts`, also collect:
- Framework (Coqui XTTS, Kokoro, Bark)
- Voice cloning needed?
- Output format (mp3, wav, opus)

If worker type is `text`, also collect:
- Serving framework (vLLM, transformers, llama.cpp)
- Streaming needed?
- Context window / max tokens

---

## Step 2 — Architecture Principles

Apply these to every worker regardless of type.

### Directory Layout

Workers live at `workers/{name}/` in the repo root.

```
workers/{name}/
├── Dockerfile
├── requirements.txt
├── entrypoint.sh           # downloads models on cold start, execs handler
├── handler.py              # runpod entry point
├── volume_paths.py         # all path constants — never inline strings
├── storage.py              # R2 upload utility
├── schemas.py              # Pydantic input/output models
├── {pipeline_name}.py      # model-specific inference logic
├── tests/
│   ├── __init__.py
│   ├── test_handler.py     # handler unit tests
│   └── test_schemas.py     # schema validation tests
└── scripts/
    └── download_models.py  # run at container start to populate volume
```

If the repo has an internal shared package, document its path and install method in the Dockerfile — the structure depends on the repo.

### Network Volume Pattern

Weights live on the network volume, not baked into the Docker image. The image stays thin (~2–4 GB). Volume path comes from the `VOLUME_ROOT` env var — set this in the RunPod template environment. Path constants belong in `volume_paths.py`; never construct paths inline anywhere else.

```python
# volume_paths.py
import os
from pathlib import Path

VOLUME_ROOT = Path(os.environ.get("VOLUME_ROOT", "/workspace/models"))

def model_dir(model_id: str) -> Path:
    return VOLUME_ROOT / model_id

def lora_path(name: str) -> Path:
    return VOLUME_ROOT / "loras" / f"{name}.safetensors"

def voice_path(voice_id: str) -> Path:
    return VOLUME_ROOT / "voices" / voice_id

def llm_path(model_id: str) -> Path:
    return VOLUME_ROOT / model_id

def hf_cache_dir() -> Path:
    return VOLUME_ROOT / "hf_cache"
```

### Entrypoint Pattern

`entrypoint.sh` runs at container start: creates volume dirs, runs the download script, then execs the handler. Downloads are skipped if files already exist (idempotent on warm start).

```bash
#!/usr/bin/env bash
set -euo pipefail

export VOLUME_ROOT="${VOLUME_ROOT:-/workspace/models}"
export HUGGINGFACE_HUB_CACHE="${VOLUME_ROOT}/hf_cache"
mkdir -p "${VOLUME_ROOT}" "${HUGGINGFACE_HUB_CACHE}"

python /app/scripts/download_models.py

# Lock HF to offline mode after downloads complete
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

exec python -u handler.py
```

### Handler Structure

Every worker uses **streaming responses via `yield`** and `return_aggregate_stream: True`.

```python
# handler.py
import traceback
import torch
import runpod
from pydantic import ValidationError
from schemas import JobInput, JobOutput

# Phase 1 — Model loading (runs once at container start, not per job)
_pipeline = None

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = MyPipeline(device="cuda" if torch.cuda.is_available() else "cpu")
        _pipeline.load()
    return _pipeline

# Phase 2 — Job handler (runs per request)
def handler(job: dict):
    try:
        inp = JobInput(**job.get("input", {}))
    except ValidationError as e:
        yield {"error": f"invalid input: {e}"}
        return

    try:
        yield {"status": "loading"}
        pipeline = _get_pipeline()

        yield {"status": "generating"}
        result = pipeline.run(inp)

        yield result.model_dump()

    except torch.cuda.OutOfMemoryError as e:
        torch.cuda.empty_cache()
        yield {"error": "oom", "detail": str(e)}

    except Exception as e:
        print(f"[handler] job {job.get('id')} failed: {e}")
        yield {"error": str(e), "traceback": traceback.format_exc()}

    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
```

**Never load models inside the handler.** Cold start is acceptable; per-request loading is not.

### Error Handling Rules

- Yield `{"error": "..."}` for recoverable failures — caller can retry
- Log with job context: `print(f"[handler] job {job['id']} failed: {e}")`
- Catch `torch.cuda.OutOfMemoryError` explicitly — emit `{"error": "oom", "detail": str(e)}`
- Always call `torch.cuda.empty_cache()` in the `finally` block
- If LoRA is loaded per-job, always `unfuse_lora()` + `unload_lora_weights()` after inference

### Job Schema

Define input/output as Pydantic models in `schemas.py`. Validate at handler entry.

```python
# schemas.py
from pydantic import BaseModel, Field
from typing import Optional

class JobInput(BaseModel):
    prompt: str
    seed: int = Field(default=-1)
    # ... type-specific fields

class JobOutput(BaseModel):
    # ... type-specific output fields
    error: Optional[str] = None
```

---

## Step 3 — CUDA Version Decision

Choose the CUDA version based on the model and its pre-built wheel availability. Mismatching CUDA versions causes silent failures or missing GPU support.

| Model / Framework | CUDA | PyTorch | Notes |
|-------------------|------|---------|-------|
| SDXL, RealVisXL, SD1.5 | 12.1 | 2.2.x | Stable, well-tested with diffusers |
| FLUX.1-dev / schnell | 12.4 | 2.4+ | FLUX requires newer torch for bfloat16 perf |
| vLLM | 12.4 | 2.4+ | vLLM wheels are built against 12.4+ |
| Coqui XTTS / Kokoro | 12.1 | 2.2.x | Older TTS libs; 12.1 is safer |
| Custom ops / flash-attn | Match flash-attn release | — | Check flash-attn release notes |

Use `runtime` image unless you need to compile C extensions (insightface, flash-attn, custom CUDA kernels) — then use `devel`.

```dockerfile
# SDXL / RealVisXL
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# FLUX / vLLM
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Anything needing C compilation
FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04
```

---

## Step 4 — Dockerfile

Order layers from least-to-most-frequently-changing. PyTorch is isolated into its own layer because it's ~2 GB and rarely changes — rebuilding it on every code push is wasteful.

```dockerfile
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN ln -sf /usr/bin/python3 /usr/bin/python

# --- Internal package (if applicable) ---
# Adjust COPY path and install command to match this repo's structure.
# Example for a packages/shared layout:
#   COPY packages/shared /app/packages/shared
#   RUN pip install --no-cache-dir -e /app/packages/shared

# --- PyTorch — isolated layer, rarely changes ---
RUN pip install --no-cache-dir \
    torch==2.2.2+cu121 xformers==0.0.25.post1 \
    --index-url https://download.pytorch.org/whl/cu121

# --- Worker dependencies ---
COPY workers/{name}/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Worker source (most frequently changed — last layer) ---
COPY workers/{name}/ /app/

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
```

Build context must always be the **repo root**, not the worker subdirectory, so all `COPY` paths resolve:
```bash
docker build -f workers/{name}/Dockerfile -t {name}:local .
```

### Type-Specific Requirements

```
# Image worker (requirements.txt)
runpod>=1.6.0
diffusers>=0.31.0,<0.32.0
transformers>=4.40.0,<4.47.0
accelerate>=0.28.0
safetensors>=0.4.2
peft>=0.10.0
huggingface_hub>=0.23.0
Pillow>=10.2.0
pydantic>=2.0
numpy>=1.20,<2.0
boto3>=1.34.0
ruff  # linting (dev only — can pin in dev-requirements.txt)

# Image worker with face detection (add to above)
opencv-python-headless
insightface
onnxruntime-gpu>=1.17.0

# TTS worker
runpod>=1.6.0
TTS>=0.22.0
boto3>=1.34.0
pydantic>=2.0

# Text generation worker
runpod>=1.6.0
vllm>=0.5.0
pydantic>=2.0
```

---

## Step 5 — Type-Specific Implementation

### Image Worker (SDXL / RealVisXL / FLUX)

```python
# {pipeline}.py
import torch
import uuid
from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler
from volume_paths import model_dir, lora_path
from storage import upload_image
from schemas import JobInput, JobOutput

class Pipeline:
    def __init__(self, device: str = "cuda"):
        self.device = device
        self._pipe = None

    def load(self) -> None:
        self._pipe = StableDiffusionXLPipeline.from_pretrained(
            str(model_dir("your-model-id")),
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            local_files_only=True,
        ).to(self.device)
        self._pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            self._pipe.scheduler.config,
            use_karras_sigmas=True,
        )
        self._pipe.enable_attention_slicing()

    def generate(self, inp: JobInput) -> JobOutput:
        lora_loaded = False
        if inp.lora_name:
            p = lora_path(inp.lora_name)
            if p.exists():
                self._pipe.load_lora_weights(str(p))
                self._pipe.fuse_lora(lora_scale=getattr(inp, "lora_scale", 0.85))
                lora_loaded = True
            else:
                print(f"[pipeline] LoRA not found: {inp.lora_name}, proceeding without")

        seed = inp.seed if inp.seed != -1 else torch.randint(0, 2**32, (1,)).item()
        gen = torch.Generator(self.device).manual_seed(seed)

        image = self._pipe(
            prompt=inp.prompt,
            negative_prompt=getattr(inp, "negative_prompt", ""),
            num_inference_steps=inp.num_inference_steps,
            guidance_scale=inp.guidance_scale,
            width=inp.width,
            height=inp.height,
            generator=gen,
        ).images[0]

        if lora_loaded:
            self._pipe.unfuse_lora()
            self._pipe.unload_lora_weights()

        url = upload_image(image, f"outputs/{uuid.uuid4()}.png")
        return JobOutput(image_url=url, seed=seed, width=inp.width, height=inp.height)
```

**LoRA key rule:** caller passes `lora_name` (e.g. `"add-detail-xl"`), worker constructs the path. Never accept full paths in job input. Always unfuse/unload after each job to prevent state bleed between requests.

### TTS Worker (Coqui XTTS / Kokoro)

```python
# handler.py (TTS)
import io, uuid, traceback
import numpy as np
import torch
import runpod
from scipy.io import wavfile
from schemas import TTSInput, TTSOutput
from volume_paths import voice_path
from storage import upload_audio

_tts = None

def _get_tts():
    global _tts
    if _tts is None:
        from TTS.api import TTS  # noqa: PLC0415
        _tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    return _tts

def handler(job: dict):
    try:
        inp = TTSInput(**job.get("input", {}))
    except Exception as e:
        yield {"error": f"invalid input: {e}"}
        return

    try:
        yield {"status": "generating"}
        tts = _get_tts()
        speaker_wav = str(voice_path(inp.voice_id)) if inp.voice_id else None

        audio = tts.tts(text=inp.text, speaker_wav=speaker_wav, language=inp.language)

        buf = io.BytesIO()
        wavfile.write(buf, 24000, np.array(audio))
        url = upload_audio(buf.getvalue(), f"audio/{uuid.uuid4()}.wav")

        yield TTSOutput(audio_url=url, duration_seconds=len(audio) / 24000).model_dump()

    except Exception as e:
        yield {"error": str(e), "traceback": traceback.format_exc()}

    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
```

### Text Generation Worker (vLLM)

```python
# handler.py (text)
import runpod
from vllm import LLM, SamplingParams
from volume_paths import llm_path
from schemas import TextInput, TextOutput

MODEL_ID = "your-model-id"

_llm = LLM(
    model=str(llm_path(MODEL_ID)),
    dtype="bfloat16",
    gpu_memory_utilization=0.90,
)

def handler(job: dict):
    try:
        inp = TextInput(**job.get("input", {}))
    except Exception as e:
        yield {"error": f"invalid input: {e}"}
        return

    try:
        params = SamplingParams(
            temperature=inp.temperature,
            max_tokens=inp.max_tokens,
            top_p=inp.top_p,
        )
        outputs = _llm.generate([inp.prompt], params)
        text = outputs[0].outputs[0].text
        yield TextOutput(
            text=text,
            tokens_generated=len(outputs[0].outputs[0].token_ids),
        ).model_dump()
    except Exception as e:
        yield {"error": str(e)}

runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
```

---

## Step 6 — Model Download Script

```python
# scripts/download_models.py
import os
from pathlib import Path
from huggingface_hub import snapshot_download

VOLUME_ROOT = Path(os.environ.get("VOLUME_ROOT", "/workspace/models"))
HF_CACHE = Path(os.environ.get("HUGGINGFACE_HUB_CACHE", str(VOLUME_ROOT / "hf_cache")))


def download_if_missing(repo_id: str, local_dir: Path, **kwargs) -> None:
    """Download a HuggingFace model snapshot only if not already present."""
    if local_dir.exists() and any(local_dir.iterdir()):
        print(f"[download] skipping {repo_id} — already present at {local_dir}")
        return
    # Clean up any partial downloads
    for ext in (".incomplete", ".tmp", ".part"):
        for f in local_dir.rglob(f"*{ext}"):
            f.unlink(missing_ok=True)
    print(f"[download] {repo_id} → {local_dir}")
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo_id, local_dir=str(local_dir), **kwargs)
    print(f"[download] done: {repo_id}")


if __name__ == "__main__":
    # Register all model downloads here.
    # HF models:
    download_if_missing(
        "SG161222/RealVisXL_V5.0",
        VOLUME_ROOT / "realvisxl-v5",
        ignore_patterns=["*.ckpt", "*.bin"],
    )
    # CivitAI / custom URLs: use requests with HF_TOKEN / CIV_API_KEY from env
```

**Download script rules:**
- Always check existence before downloading — script must be idempotent (safe to run on warm start)
- Clean up `.incomplete` / `.tmp` / `.part` files from interrupted downloads before retrying
- Use `HF_HUB_DISABLE_XET=1` env var if you hit segfaults on XET transfer
- CivitAI: authenticate via `Authorization: Bearer {CIV_API_KEY}` header or `?token=` query param — key comes from env, never hardcoded

---

## Step 7 — R2 Upload Utility

```python
# storage.py
import io
import os
import boto3
from PIL import Image

_s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
_BUCKET = os.environ["R2_BUCKET_NAME"]
_CDN    = os.environ["CDN_BASE_URL"]


def upload_image(image: Image.Image, key: str, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    buf.seek(0)
    _s3.upload_fileobj(buf, _BUCKET, key, ExtraArgs={"ContentType": f"image/{fmt.lower()}"})
    return f"{_CDN}/{key}"


def upload_audio(audio_bytes: bytes, key: str, content_type: str = "audio/wav") -> str:
    _s3.upload_fileobj(io.BytesIO(audio_bytes), _BUCKET, key, ExtraArgs={"ContentType": content_type})
    return f"{_CDN}/{key}"
```

All credentials from env vars — injected via RunPod template environment. Never hardcode.

---

## Step 8 — Tests

Every worker ships with a `tests/` directory. Tests run in CI with CPU torch (no GPU required). Mock any external calls (model loads, R2 uploads).

```python
# tests/test_schemas.py
from schemas import JobInput, JobOutput

def test_job_input_defaults():
    inp = JobInput(prompt="test prompt")
    assert inp.seed == -1

def test_job_input_rejects_empty_prompt():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        JobInput(prompt="")  # adjust to your actual validation rules
```

```python
# tests/test_handler.py
import pytest
from unittest.mock import patch, MagicMock

def test_handler_invalid_input():
    # Import handler module; mock model load so it doesn't run
    with patch("handler._get_pipeline") as mock_pipeline:
        from handler import handler
        results = list(handler({"id": "t-1", "input": {"bad_field": 1}}))
        assert results[0].get("error") is not None

def test_handler_oom_returns_error():
    import torch
    with patch("handler._get_pipeline") as mock_pipeline:
        mock_pl = MagicMock()
        mock_pl.run.side_effect = torch.cuda.OutOfMemoryError("fake OOM")
        mock_pipeline.return_value = mock_pl
        from handler import handler
        results = list(handler({"id": "t-2", "input": {}}))
        assert any(r.get("error") == "oom" for r in results)
```

---

## Step 9 — GitHub Actions CI/CD

Every worker gets `.github/workflows/publish-{name}.yml`. Pipeline: **lint → unit tests → build + push to GHCR → update RunPod template via API**.

```yaml
name: publish-{name}

on:
  push:
    branches: [main]
    paths:
      - "workers/{name}/**"
      - ".github/workflows/publish-{name}.yml"
      # Add any internal shared packages this worker depends on:
      # - "packages/shared/**"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Lint Python (ruff)
        uses: astral-sh/ruff-action@v3
        with:
          src: workers/{name}

      - name: Lint Dockerfile (hadolint)
        uses: hadolint/hadolint-action@v3.1.0
        with:
          dockerfile: workers/{name}/Dockerfile

  unit-tests:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install CPU torch + worker deps
        run: |
          pip install torch --index-url https://download.pytorch.org/whl/cpu
          pip install -r workers/{name}/requirements.txt pytest
          # Uncomment if this worker depends on an internal package:
          # pip install -e packages/shared
        env:
          PYTHONPATH: workers/{name}

      - name: Run tests
        run: pytest workers/{name}/tests/ -v --tb=short
        env:
          PYTHONPATH: workers/{name}

  build-and-push:
    runs-on: ubuntu-latest
    needs: unit-tests
    outputs:
      image: ${{ steps.meta.outputs.tags }}
      sha_tag: ghcr.io/${{ github.repository_owner }}/${{ github.event.repository.name }}/{name}:sha-${{ github.sha }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/${{ github.event.repository.name }}/{name}
          tags: |
            type=raw,value=latest
            type=sha,prefix=sha-,format=short

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: workers/{name}/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    runs-on: ubuntu-latest
    needs: build-and-push
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Update RunPod template
        env:
          RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
          RUNPOD_TEMPLATE_ID: ${{ secrets.RUNPOD_{NAME}_TEMPLATE_ID }}
          IMAGE_TAG: ghcr.io/${{ github.repository_owner }}/${{ github.event.repository.name }}/{name}:sha-${{ github.sha }}
        run: python .github/scripts/update_runpod_template.py
```

### RunPod Template Update Script

Produce this shared helper at `.github/scripts/update_runpod_template.py`. It fetches the current template (preserving all fields), upserts any secrets into the env array, and updates only the image name — so the RunPod UI is never the source of truth for config.

```python
# .github/scripts/update_runpod_template.py
"""
Update a RunPod serverless template's image via GraphQL API.
Preserves all existing template fields; only changes imageName.
Optionally upserts env vars from INJECT_ENV (JSON-encoded key=value pairs).

Required env vars:
  RUNPOD_API_KEY       RunPod API key
  RUNPOD_TEMPLATE_ID   Template ID to update
  IMAGE_TAG            Full image reference (ghcr.io/owner/repo/worker:sha-abc1234)

Optional env vars:
  INJECT_ENV           JSON object of env vars to upsert, e.g. '{"CIV_API_KEY":"abc"}'
"""
import json
import os
import sys
import urllib.request

API = "https://api.runpod.io/graphql"
API_KEY = os.environ["RUNPOD_API_KEY"]
TEMPLATE_ID = os.environ["RUNPOD_TEMPLATE_ID"]
IMAGE_TAG = os.environ["IMAGE_TAG"]
INJECT_ENV = json.loads(os.environ.get("INJECT_ENV", "{}"))


def graphql(query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(1)
    return data


def upsert_env(env_list: list[dict], updates: dict) -> list[dict]:
    """Upsert key/value pairs into a RunPod env list [{key, value}, ...]."""
    env = {e["key"]: e["value"] for e in env_list}
    env.update(updates)
    return [{"key": k, "value": v} for k, v in env.items()]


# 1. Fetch current template
fetch_q = """
query GetTemplate($id: String!) {
  myself {
    podTemplates(ids: [$id]) {
      id
      name
      imageName
      dockerArgs
      containerDiskInGb
      volumeInGb
      volumeMountPath
      ports
      env { key value }
      startJupyter
      startSsh
    }
  }
}
"""
result = graphql(fetch_q, {"id": TEMPLATE_ID})
templates = result["data"]["myself"]["podTemplates"]
if not templates:
    print(f"Template {TEMPLATE_ID} not found", file=sys.stderr)
    sys.exit(1)

tmpl = templates[0]
print(f"Updating template: {tmpl['name']} ({TEMPLATE_ID})")
print(f"  {tmpl['imageName']}  →  {IMAGE_TAG}")

# 2. Upsert any injected env vars
updated_env = upsert_env(tmpl.get("env") or [], INJECT_ENV)

# 3. Mutate — preserve all fields, update only imageName (and env)
save_q = """
mutation SaveTemplate($input: PodTemplateInput!) {
  saveTemplate(input: $input) {
    id
    imageName
  }
}
"""
save_result = graphql(save_q, {
    "input": {
        "id": TEMPLATE_ID,
        "name": tmpl["name"],
        "imageName": IMAGE_TAG,
        "dockerArgs": tmpl.get("dockerArgs", ""),
        "containerDiskInGb": tmpl["containerDiskInGb"],
        "volumeInGb": tmpl.get("volumeInGb", 0),
        "volumeMountPath": tmpl.get("volumeMountPath", "/workspace"),
        "ports": tmpl.get("ports", ""),
        "env": updated_env,
        "startJupyter": tmpl.get("startJupyter", False),
        "startSsh": tmpl.get("startSsh", False),
    }
})

updated = save_result["data"]["saveTemplate"]
print(f"Done. Template {updated['id']} now uses: {updated['imageName']}")
```

**Key workflow decisions:**
- `lint` runs first — fail fast before spending build minutes
- hadolint catches Dockerfile issues (unpinned packages, missing `--no-install-recommends`, etc.)
- ruff catches Python style and import issues without needing a GPU runner
- Tests always use CPU torch (`--index-url https://download.pytorch.org/whl/cpu`) — no GPU runner needed
- Build context is always `.` (repo root) so all `COPY` paths resolve
- GHCR images are tagged `latest` + `sha-{short-sha}` for precise version tracking
- `type=gha` cache keeps torch/xformers layer cached between workflow runs
- `environment: production` gates the deploy job behind branch protection
- Template update fetches all fields first and preserves them — the CI/CD workflow is the source of truth, not the RunPod UI

**Required GitHub secrets:**

| Secret | Where |
|--------|-------|
| `RUNPOD_API_KEY` | Repo or org secrets |
| `RUNPOD_{NAME}_TEMPLATE_ID` | Repo secrets |
| `HF_TOKEN` (if needed) | Injected via `INJECT_ENV` in deploy step |
| `CIV_API_KEY` (if needed) | Injected via `INJECT_ENV` in deploy step |

To inject env vars into the template via CI, pass them in the deploy step:
```yaml
- name: Update RunPod template
  env:
    RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
    RUNPOD_TEMPLATE_ID: ${{ secrets.RUNPOD_{NAME}_TEMPLATE_ID }}
    IMAGE_TAG: ...
    INJECT_ENV: >-
      {
        "CIV_API_KEY": "${{ secrets.CIV_API_KEY }}",
        "HF_TOKEN": "${{ secrets.HF_TOKEN }}"
      }
  run: python .github/scripts/update_runpod_template.py
```

---

## Step 10 — Local Smoke Test

```python
# scripts/test_local.py
import sys
import os

sys.path.insert(0, ".")

# Point at local model weights
os.environ["VOLUME_ROOT"] = "/path/to/local/models"
# Mock R2 credentials so storage.py doesn't crash on import
os.environ.setdefault("R2_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("R2_ACCESS_KEY_ID", "test")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("R2_BUCKET_NAME", "test")
os.environ.setdefault("CDN_BASE_URL", "http://localhost")

from handler import handler  # noqa: E402

test_job = {
    "id": "test-001",
    "input": {
        # fill in test input matching your schema
    },
}

results = list(handler(test_job))
final = results[-1]

print(f"Yields: {results[:-1]}")
print(f"Final:  {final}")
assert "error" not in final, f"Handler returned error: {final.get('error')}"
print("smoke test passed")
```

Run before pushing:
```bash
PYTHONPATH=workers/{name} python workers/{name}/scripts/test_local.py
```

---

## Output Checklist

Before finishing, confirm:
- [ ] `volume_paths.py` centralizes all path construction — `VOLUME_ROOT` defaults to `/workspace/models`
- [ ] Model loading is outside the handler function (global, lazy-init)
- [ ] Handler uses `yield` for streaming — `return_aggregate_stream: True` in `serverless.start`
- [ ] `torch.cuda.OutOfMemoryError` caught explicitly, yields `{"error": "oom"}`
- [ ] `torch.cuda.empty_cache()` called in `finally` block
- [ ] LoRA (if used) is unfused + unloaded after each job
- [ ] `entrypoint.sh` downloads models before starting handler, sets `HF_HUB_OFFLINE=1` after
- [ ] Download script is idempotent — skips files that already exist
- [ ] CUDA version chosen based on model requirements (see decision table)
- [ ] Dockerfile uses `runtime` unless C extensions require `devel`
- [ ] PyTorch in an isolated layer before worker deps
- [ ] `hadolint ignore` comments added where Dockerfile rules are intentionally violated
- [ ] Build context is repo root (`.`), not the worker subdirectory
- [ ] `storage.py` uses env vars for all credentials
- [ ] `tests/` directory produced with schema tests and handler tests (OOM, invalid input)
- [ ] GitHub Actions workflow: lint (ruff + hadolint) → tests → build+push → RunPod template update
- [ ] GHCR image tagged `latest` + `sha-{short-sha}`
- [ ] `.github/scripts/update_runpod_template.py` fetches all fields before mutating
- [ ] `INJECT_ENV` used in deploy step for any secrets that belong in the RunPod template env
- [ ] Local smoke test script produced
- [ ] Worker added to `STATUS.md` as `📋 Planned`
