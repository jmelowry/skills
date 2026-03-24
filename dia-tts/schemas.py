from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class JobInput(BaseModel):
    script: str = Field(..., description="Dialogue script with [S1]/[S2] speaker tags")
    seed: Optional[int] = Field(None, description="Random seed for reproducible output")
    cfg_scale: float = Field(2.0, ge=0.5, le=10.0)
    temperature: float = Field(0.8, ge=0.0, le=2.0)
    top_k: int = Field(50, ge=1, le=200)
    prefix_s1_b64: Optional[str] = Field(
        None, description="Base64-encoded WAV for S1 voice cloning (5–15s reference)"
    )
    prefix_s2_b64: Optional[str] = Field(
        None, description="Base64-encoded WAV for S2 voice cloning (5–15s reference)"
    )


class JobOutput(BaseModel):
    audio_b64: str = Field(..., description="Base64-encoded WAV bytes")
    sample_rate: int = Field(..., description="Sample rate in Hz (44100)")
    duration_seconds: float = Field(..., description="Audio duration in seconds")
    error: Optional[str] = None
