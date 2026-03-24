# Prompt: Deploy Dia2 TTS to RunPod Serverless (Baked Image)

## Context to give the AI before using this prompt

Paste this entire document into a Claude Code session or a new Claude chat. It contains everything needed to produce a fully working, production-ready RunPod Serverless worker for Dia2 TTS.

---

## THE PROMPT

You are an expert in RunPod Serverless deployment and Python ML inference APIs. I need you to produce all files required to build and deploy a fully-baked Docker image for the **Dia2 TTS model by Nari Labs** as a RunPod Serverless worker. The image must be under 10GB compressed.

### What Dia2 Is

- GitHub: `https://github.com/nari-labs/dia2`
- HuggingFace: `nari-labs/Dia2-1B` and `nari-labs/Dia2-2B`
- A streaming dialogue TTS model. Generates realistic multi-speaker audio in a single pass.
- Uses `[S1]` / `[S2]` speaker tags in the text script.
- Supports voice conditioning (cloning) via `--prefix-speaker-1` and `--prefix-speaker-2` WAV files (5–15s each), transcribed internally by Whisper.
- Supports nonverbal tags: `(laughs)`, `(sighs)`, `(coughs)`, `(gasps)`, `(screams)`, `(whispers)`, etc.
- Output: WAV audio at 44.1kHz (via Mimi codec from Kyutai).
- Max generation: ~2 minutes of audio per call.
- **Requires CUDA 12.8+ drivers** (critical — older CUDA will fail).
- Python API:

```python
from dia2 import Dia2, GenerationConfig, SamplingConfig

dia = Dia2.from_repo("nari-labs/Dia2-1B", device="cuda", dtype="bfloat16")
config = GenerationConfig(
    cfg_scale=2.0,
    audio=SamplingConfig(temperature=0.8, top_k=50),
    use_cuda_graph=True,
)
result = dia.generate("[S1] Hello! [S2] Hey there.", config=config, verbose=False)
# result.waveform is a torch.Tensor, result.sample_rate is the sample rate
```

- `GenerationResult` exposes: `waveform` (tensor), `sample_rate`, `mimi_tokens`, and word-level `timestamps`.
- To fix a voice across calls, use a seed: `torch.manual_seed(42)` before `.generate()`.
- For voice cloning, pass `prefix_audio_s1` and `prefix_audio_s2` as numpy arrays or file paths.

### Image Size Strategy

- **Use `nari-labs/Dia2-1B`** (not 2B) for the baked image — the 1B model weights in bfloat16 are ~2GB vs ~4GB for 2B.
- Target base image: `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04` — lean, no PyTorch bundled.
- Install PyTorch from the CU128 wheel index at build time.
- Download and cache Dia2-1B weights + Mimi codec into the image at build time using a Python script that calls `Dia2.from_repo(...)` and then exits (this populates the HuggingFace cache).
- Set `HF_HOME=/app/hf_cache` and `TRANSFORMERS_CACHE=/app/hf_cache` so the cache lands in a known path.
- Use `.dockerignore` to exclude anything not needed.
- Target compressed image size: **under 10GB**.

### What I Need You to Produce

Please produce all of the following files, each complete and production-ready:

---

#### 1. `handler.py` — RunPod Serverless Handler

The RunPod entry point. Must:

- Import `runpod` and define `handler(job)` following the RunPod Serverless handler spec.
- Load Dia2-1B **once at module level** (not inside the handler function) so it's warm across calls.
- Accept this JSON input schema:

```json
{
  "input": {
    "script": "[S1] Hello world. [S2] How are you today? (laughs)",
    "seed": 42,
    "cfg_scale": 2.0,
    "temperature": 0.8,
    "top_k": 50,
    "prefix_s1_b64": "<optional base64-encoded WAV for S1 voice>",
    "prefix_s2_b64": "<optional base64-encoded WAV for S2 voice>"
  }
}
```

- Return output:

```json
{
  "audio_b64": "<base64-encoded WAV bytes>",
  "sample_rate": 44100,
  "duration_seconds": 12.3
}
```

- Decode `prefix_s1_b64` and `prefix_s2_b64` from base64 to temp WAV files if provided, pass to `.generate()` for voice cloning.
- Set `torch.manual_seed(seed)` before generation when seed is provided.
- Encode the output waveform as a WAV file in memory (using `soundfile` or `scipy.io.wavfile`) and return as base64.
- Handle errors gracefully, return `{"error": str(e)}` on failure.
- Log generation duration.

---

#### 2. `Dockerfile`

Must:

- Base: `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`
- Install system deps: `python3.11`, `python3-pip`, `git`, `ffmpeg`, `libsndfile1`
- Install PyTorch from CUDA 12.8 wheel index: `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128`
- Install `uv`, then use it to install `dia2` from GitHub: `pip install git+https://github.com/nari-labs/dia2.git`
- Install additional Python deps: `runpod`, `soundfile`, `scipy`, `numpy`, `faster-whisper` (used internally by dia2 for prefix transcription)
- Set env vars: `HF_HOME=/app/hf_cache`, `TRANSFORMERS_CACHE=/app/hf_cache`, `PYTHONUNBUFFERED=1`
- Copy a `download_model.py` script and run it during build to bake the weights:
  ```
  RUN python3 download_model.py
  ```
- Copy `handler.py` last (so weight layer is cached separately in Docker layer cache).
- Set `CMD ["python3", "-u", "handler.py"]`

---

#### 3. `download_model.py`

A standalone script run at Docker build time. Must:

- Call `Dia2.from_repo("nari-labs/Dia2-1B", device="cpu", dtype="float32")` — use CPU here since there's no GPU at build time.
- This will download and cache all weights + Mimi codec to `HF_HOME`.
- Print progress and exit cleanly.
- Include a note: GPU/bfloat16 are used at runtime, not at build time.

---

#### 4. `requirements.txt`

Pinned dependencies for everything NOT installed via wheel URL or git. Include:
- `runpod`
- `soundfile`
- `scipy`
- `numpy`
- `faster-whisper`
- `huggingface_hub`

---

#### 5. `build_and_push.sh`

A shell script that:

- Accepts `DOCKER_USER` and `IMAGE_TAG` as env vars (with defaults).
- Runs `docker build` with `--platform linux/amd64`.
- Runs `docker push`.
- Prints the final image name for use in RunPod.

---

#### 6. `test_local.py`

A local test script that:

- Simulates a RunPod job payload.
- Calls `handler({"input": {...}})` directly.
- Writes the returned audio to `test_output.wav`.
- Useful for validating the handler before pushing the image.

---

#### 7. `README.md`

A concise deployment guide covering:

- Prerequisites (Docker, NVIDIA driver ≥ CUDA 12.8, RunPod account)
- How to build and push: `./build_and_push.sh`
- How to deploy on RunPod:
  - Recommended GPU: RTX 4090 (24GB), A4000 (16GB), or L4 (24GB) — all have plenty of VRAM for 1B model (~3–4GB at runtime)
  - Set `RUNPOD_INIT_TIMEOUT=300` env var in RunPod endpoint config (model load can take 30–60s cold)
  - Recommended endpoint settings: 0 active workers (pure flex/serverless), max workers 3
- API call example with curl showing base64 encode/decode of prefix WAVs
- How to scale to Dia2-2B via network volume (as an upgrade path)
- Note on the 2-minute generation limit and chunking strategy for longer content

---

### Additional Requirements

- All Python should be type-hinted where it aids clarity.
- No Gradio, no web UI — pure RunPod handler.
- The handler must be re-entrant safe (model loaded once at module init, handler called N times).
- Do not use `uv run` in the Docker entrypoint — use plain `python3` since `uv` is for dev workflow only.
- Output WAV should be 44100 Hz mono (Mimi codec default).
- If `use_cuda_graph=True` causes issues on certain GPUs (e.g., RTX 5000 series), add a fallback with `use_cuda_graph=False`.

### Constraints

- Image must stay **under 10GB compressed**. If you identify a risk of exceeding this, flag it and suggest a mitigation (e.g., using a slimmer base, or switching to network volume for weights).
- CUDA version **must be 12.8+**. Do not use older CUDA base images.
- Python **3.10 minimum**, prefer 3.11.
- Apache 2.0 license compliant throughout.
