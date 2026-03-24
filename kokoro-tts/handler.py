from __future__ import annotations

import base64
import io
import subprocess
import time
import traceback
from typing import Dict

import numpy as np
import runpod
import soundfile as sf
import torch
from pydantic import ValidationError

from schemas import JobInput, JobOutput, SpeakerSegment

# ── Pipeline cache (keyed by lang_code, loaded lazily per request) ────────────

_pipelines: Dict[str, object] = {}

SAMPLE_RATE = 24000

# Voice prefix → lang_code mapping for auto-detection in multi-speaker mode
_VOICE_LANG: Dict[str, str] = {
    "af_": "a",
    "am_": "a",
    "bf_": "b",
    "bm_": "b",
}


def _lang_for_voice(voice: str) -> str:
    """Infer lang_code from voice prefix (e.g. 'af_heart' → 'a')."""
    for prefix, code in _VOICE_LANG.items():
        if voice.startswith(prefix):
            return code
    return "a"  # default to American English


def _get_pipeline(lang_code: str) -> object:
    global _pipelines
    if lang_code not in _pipelines:
        from kokoro import KPipeline

        print(f"[handler] Loading Kokoro pipeline for lang_code='{lang_code}'...", flush=True)
        t0 = time.time()
        _pipelines[lang_code] = KPipeline(lang_code=lang_code)
        print(f"[handler] Pipeline ready in {time.time() - t0:.1f}s", flush=True)
    return _pipelines[lang_code]


# ── Audio encoding helpers ─────────────────────────────────────────────────────


def _to_wav_bytes(audio: np.ndarray) -> bytes:
    """Encode a float32 numpy array to WAV bytes (PCM_16)."""
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to MP3 bytes via ffmpeg (libmp3lame, VBR q=2)."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0",
         "-codec:a", "libmp3lame", "-q:a", "2", "-f", "mp3", "pipe:1"],
        input=wav_bytes,
        capture_output=True,
        check=True,
    )
    return result.stdout


# ── Synthesis helpers ──────────────────────────────────────────────────────────


def _synthesise_segment(pipeline: object, segment: SpeakerSegment) -> np.ndarray:
    """Run the Kokoro pipeline on one segment and return the concatenated audio."""
    chunks = []
    for _graphemes, _phonemes, audio in pipeline(segment.text, voice=segment.voice, speed=segment.speed):
        if audio is not None and len(audio) > 0:
            chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)


# ── Job handler ────────────────────────────────────────────────────────────────


def handler(job: dict):
    try:
        inp = JobInput(**job.get("input", {}))
    except ValidationError as e:
        yield {"error": f"invalid input: {e}"}
        return

    try:
        yield {"status": "loading"}

        if inp.seed is not None:
            torch.manual_seed(inp.seed)

        yield {"status": "generating"}

        t0 = time.time()

        if inp.segments:
            # Multi-speaker mode: each segment may use its own voice and lang_code
            audio_parts: list[np.ndarray] = []
            for seg in inp.segments:
                lang_code = _lang_for_voice(seg.voice)
                pipeline = _get_pipeline(lang_code)
                part = _synthesise_segment(pipeline, seg)
                if len(part) > 0:
                    audio_parts.append(part)
            audio = np.concatenate(audio_parts) if audio_parts else np.zeros(0, dtype=np.float32)
        else:
            # Single-speaker mode
            pipeline = _get_pipeline(inp.lang_code)
            seg = SpeakerSegment(text=inp.text, voice=inp.voice, speed=inp.speed)  # type: ignore[arg-type]
            audio = _synthesise_segment(pipeline, seg)

        elapsed = time.time() - t0
        print(f"[handler] Generated in {elapsed:.1f}s (job {job.get('id')})", flush=True)

        wav_bytes = _to_wav_bytes(audio)
        if inp.output_format == "mp3":
            audio_bytes = _wav_to_mp3(wav_bytes)
        else:
            audio_bytes = wav_bytes

        duration = round(len(audio) / SAMPLE_RATE, 2)

        yield JobOutput(
            audio_b64=base64.b64encode(audio_bytes).decode("utf-8"),
            sample_rate=SAMPLE_RATE,
            duration_seconds=duration,
            output_format=inp.output_format,
        ).model_dump()

    except torch.cuda.OutOfMemoryError as e:
        torch.cuda.empty_cache()
        yield {"error": "oom", "detail": str(e)}

    except Exception as e:
        print(f"[handler] job {job.get('id')} failed: {e}", flush=True)
        yield {"error": str(e), "traceback": traceback.format_exc()}

    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
