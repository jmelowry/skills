import pytest
from pydantic import ValidationError

from schemas import JobInput, JobOutput, SpeakerSegment


def test_single_speaker_defaults():
    inp = JobInput(text="Hello, world.")
    assert inp.voice == "af_heart"
    assert inp.speed == 1.0
    assert inp.lang_code == "a"
    assert inp.segments is None
    assert inp.seed is None
    assert inp.output_format == "mp3"


def test_single_speaker_all_fields():
    inp = JobInput(
        text="Good morning.",
        voice="am_michael",
        speed=1.2,
        lang_code="a",
        seed=42,
        output_format="wav",
    )
    assert inp.voice == "am_michael"
    assert inp.speed == 1.2
    assert inp.seed == 42
    assert inp.output_format == "wav"


def test_multi_speaker_segments():
    inp = JobInput(
        segments=[
            {"text": "Hello there.", "voice": "af_heart", "speed": 1.0},
            {"text": "Hi back.", "voice": "am_michael", "speed": 0.9},
        ]
    )
    assert len(inp.segments) == 2
    assert inp.segments[0].voice == "af_heart"
    assert inp.segments[1].voice == "am_michael"


def test_multi_speaker_segments_override_text():
    """segments field takes precedence; text can also be absent."""
    inp = JobInput(
        segments=[{"text": "Only this segment.", "voice": "bf_emma"}]
    )
    assert inp.text is None
    assert len(inp.segments) == 1


def test_error_when_neither_text_nor_segments():
    with pytest.raises(ValidationError, match="text.*segments|segments.*text|Provide either"):
        JobInput(voice="af_heart")


def test_speed_bounds():
    with pytest.raises(ValidationError):
        JobInput(text="Hi.", speed=0.1)  # below minimum 0.5

    with pytest.raises(ValidationError):
        JobInput(text="Hi.", speed=5.0)  # above maximum 2.0


def test_segment_speed_bounds():
    with pytest.raises(ValidationError):
        SpeakerSegment(text="Hi.", voice="af_heart", speed=0.1)

    with pytest.raises(ValidationError):
        SpeakerSegment(text="Hi.", voice="af_heart", speed=3.0)


def test_output_format_validation():
    with pytest.raises(ValidationError):
        JobInput(text="Hi.", output_format="ogg")  # type: ignore[arg-type]


def test_job_output_fields():
    out = JobOutput(
        audio_b64="dGVzdA==",
        sample_rate=24000,
        duration_seconds=2.5,
        output_format="mp3",
    )
    assert out.sample_rate == 24000
    assert out.duration_seconds == 2.5
    assert out.output_format == "mp3"
    assert out.error is None
