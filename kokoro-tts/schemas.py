from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SpeakerSegment(BaseModel):
    text: str = Field(..., description="Text to synthesise for this segment")
    voice: str = Field("af_heart", description="Kokoro voice preset for this segment")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Speech rate multiplier")


class JobInput(BaseModel):
    # Single-speaker mode: provide text + voice
    text: Optional[str] = Field(None, description="Text to synthesise (single-speaker mode)")
    voice: str = Field("af_heart", description="Voice for single-speaker mode")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Speech rate multiplier")
    lang_code: str = Field(
        "a",
        description="Language/accent code: 'a'=American English, 'b'=British English",
    )
    # Multi-speaker mode: provide segments (overrides text/voice)
    segments: Optional[List[SpeakerSegment]] = Field(
        None,
        description="List of speaker segments for multi-speaker synthesis (overrides text/voice)",
    )
    seed: Optional[int] = Field(None, description="Random seed for reproducible output")
    output_format: Literal["mp3", "wav"] = Field("mp3", description="Output audio format")

    @model_validator(mode="after")
    def require_text_or_segments(self) -> "JobInput":
        if self.text is None and self.segments is None:
            raise ValueError("Provide either 'text' (single-speaker) or 'segments' (multi-speaker)")
        return self


class JobOutput(BaseModel):
    audio_b64: str = Field(..., description="Base64-encoded audio bytes")
    sample_rate: int = Field(..., description="Sample rate in Hz (always 24000)")
    duration_seconds: float = Field(..., description="Audio duration in seconds")
    output_format: str = Field(..., description="Audio format: 'mp3' or 'wav'")
    error: Optional[str] = None
