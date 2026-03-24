from __future__ import annotations

import base64
import io
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional

import runpod
import soundfile as sf
import torch
from pydantic import ValidationError

from schemas import JobInput, JobOutput

# ── Model (loaded once at container start, reused across all requests) ─────────

_model = None


def _get_model():
    global _model
    if _model is None:
        from dia2 import Dia2

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = "bfloat16" if device == "cuda" else "float32"
        print(f"[handler] Loading Dia2-1B on {device}/{dtype}...", flush=True)
        t0 = time.time()
        _model = Dia2.from_repo("nari-labs/Dia2-1B", device=device, dtype=dtype)
        print(f"[handler] Model ready in {time.time() - t0:.1f}s", flush=True)
    return _model


# ── Job handler ────────────────────────────────────────────────────────────────


def handler(job: dict):
    try:
        inp = JobInput(**job.get("input", {}))
    except ValidationError as e:
        yield {"error": f"invalid input: {e}"}
        return

    tmp_files: list[str] = []
    try:
        yield {"status": "loading"}
        model = _get_model()

        prefix_s1 = _decode_prefix(inp.prefix_s1_b64, "prefix_s1", tmp_files)
        prefix_s2 = _decode_prefix(inp.prefix_s2_b64, "prefix_s2", tmp_files)

        if inp.seed is not None:
            torch.manual_seed(inp.seed)

        yield {"status": "generating"}

        from dia2 import GenerationConfig, SamplingConfig

        config = GenerationConfig(
            cfg_scale=inp.cfg_scale,
            audio=SamplingConfig(temperature=inp.temperature, top_k=inp.top_k),
            use_cuda_graph=True,
        )

        t0 = time.time()
        try:
            result = model.generate(
                inp.script,
                config=config,
                prefix_audio_s1=prefix_s1,
                prefix_audio_s2=prefix_s2,
                verbose=False,
            )
        except RuntimeError as e:
            # RTX 5000-series and some other GPUs don't support CUDA graphs
            if "graph" in str(e).lower() or "cuda_graph" in str(e).lower():
                print(f"[handler] CUDA graph failed ({e}) — retrying without", flush=True)
                fallback = GenerationConfig(
                    cfg_scale=inp.cfg_scale,
                    audio=SamplingConfig(temperature=inp.temperature, top_k=inp.top_k),
                    use_cuda_graph=False,
                )
                result = model.generate(
                    inp.script,
                    config=fallback,
                    prefix_audio_s1=prefix_s1,
                    prefix_audio_s2=prefix_s2,
                    verbose=False,
                )
            else:
                raise

        elapsed = time.time() - t0
        print(f"[handler] Generated in {elapsed:.1f}s (job {job.get('id')})", flush=True)

        waveform = result.waveform
        if isinstance(waveform, torch.Tensor):
            waveform = waveform.cpu().numpy()
        if waveform.ndim > 1:
            waveform = waveform.squeeze()

        buf = io.BytesIO()
        sf.write(buf, waveform, result.sample_rate, format="WAV", subtype="PCM_16")
        audio_bytes = buf.getvalue()

        yield JobOutput(
            audio_b64=base64.b64encode(audio_bytes).decode("utf-8"),
            sample_rate=result.sample_rate,
            duration_seconds=round(len(waveform) / result.sample_rate, 2),
        ).model_dump()

    except torch.cuda.OutOfMemoryError as e:
        torch.cuda.empty_cache()
        yield {"error": "oom", "detail": str(e)}

    except Exception as e:
        print(f"[handler] job {job.get('id')} failed: {e}", flush=True)
        yield {"error": str(e), "traceback": traceback.format_exc()}

    finally:
        for f in tmp_files:
            try:
                Path(f).unlink(missing_ok=True)
            except Exception:
                pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _decode_prefix(
    b64_str: Optional[str], name: str, tmp_files: list[str]
) -> Optional[str]:
    """Decode a base64-encoded WAV to a temp file. Returns path or None."""
    if not b64_str:
        return None
    try:
        wav_bytes = base64.b64decode(b64_str)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix=f"{name}_") as f:
            f.write(wav_bytes)
            tmp_files.append(f.name)
            return f.name
    except Exception as e:
        print(f"[handler] Failed to decode {name}: {e}", flush=True)
        return None


runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
