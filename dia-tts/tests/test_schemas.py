import pytest
from pydantic import ValidationError

from schemas import JobInput, JobOutput


def test_job_input_defaults():
    inp = JobInput(script="[S1] Hello. [S2] Hi.")
    assert inp.cfg_scale == 2.0
    assert inp.temperature == 0.8
    assert inp.top_k == 50
    assert inp.seed is None
    assert inp.prefix_s1_b64 is None
    assert inp.prefix_s2_b64 is None


def test_job_input_all_fields():
    inp = JobInput(
        script="[S1] Test.",
        seed=42,
        cfg_scale=3.0,
        temperature=0.5,
        top_k=30,
        prefix_s1_b64="dGVzdA==",
        prefix_s2_b64="dGVzdA==",
    )
    assert inp.seed == 42
    assert inp.cfg_scale == 3.0
    assert inp.prefix_s1_b64 == "dGVzdA=="


def test_job_input_requires_script():
    with pytest.raises(ValidationError):
        JobInput()  # type: ignore[call-arg]


def test_job_input_cfg_scale_bounds():
    with pytest.raises(ValidationError):
        JobInput(script="[S1] Hi.", cfg_scale=0.1)  # below minimum 0.5

    with pytest.raises(ValidationError):
        JobInput(script="[S1] Hi.", cfg_scale=99.0)  # above maximum 10.0


def test_job_output_fields():
    out = JobOutput(audio_b64="dGVzdA==", sample_rate=44100, duration_seconds=1.5)
    assert out.sample_rate == 44100
    assert out.duration_seconds == 1.5
    assert out.error is None
