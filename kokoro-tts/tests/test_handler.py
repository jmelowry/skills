"""
Handler unit tests — run on CPU in CI (no GPU, no real model).

conftest.py mocks runpod and kokoro before any import, so handler.py can be
imported without triggering serverless.start() or loading a real pipeline.

These tests require torch (CPU build is fine). They are skipped gracefully
if torch is not installed.
"""
import sys
from unittest.mock import MagicMock, patch


torch = pytest = None

try:
    import pytest
    import torch
except ImportError:
    pass


def _fresh_handler():
    """Return a fresh import of handler (clearing cached module and pipeline state)."""
    for mod in list(sys.modules.keys()):
        if mod in ("handler",):
            del sys.modules[mod]
    import handler as h  # noqa: PLC0415

    # Reset pipeline cache so each test starts clean
    h._pipelines.clear()
    return h


if pytest is not None:
    pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")


def test_handler_missing_text_and_segments():
    if torch is None:
        return
    h = _fresh_handler()
    results = list(h.handler({"id": "t-1", "input": {}}))
    assert any("error" in r for r in results), f"Expected error, got: {results}"


def test_handler_invalid_speed():
    if torch is None:
        return
    h = _fresh_handler()
    results = list(h.handler({"id": "t-2", "input": {"text": "Hi.", "speed": 99.0}}))
    assert any("error" in r for r in results)


def test_handler_single_speaker_wav():
    """Single-speaker mode returns audio_b64 with WAV format."""
    if torch is None:
        return
    h = _fresh_handler()
    results = list(h.handler({"id": "t-3", "input": {"text": "Hello.", "output_format": "wav"}}))
    final = [r for r in results if "audio_b64" in r]
    assert final, f"Expected audio result, got: {results}"
    assert final[0]["output_format"] == "wav"
    assert final[0]["sample_rate"] == 24000
    assert final[0]["duration_seconds"] >= 0


def test_handler_single_speaker_mp3():
    """Single-speaker mode with MP3 output calls ffmpeg subprocess."""
    if torch is None:
        return
    h = _fresh_handler()
    fake_mp3 = b"ID3" + b"\x00" * 128  # minimal fake MP3 bytes

    with patch("handler.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=fake_mp3, returncode=0)
        results = list(h.handler({"id": "t-4", "input": {"text": "Hello.", "output_format": "mp3"}}))

    final = [r for r in results if "audio_b64" in r]
    assert final, f"Expected audio result, got: {results}"
    assert final[0]["output_format"] == "mp3"
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "ffmpeg" in cmd
    assert "libmp3lame" in cmd


def test_handler_multi_speaker():
    """Multi-speaker mode synthesises each segment and concatenates audio."""
    if torch is None:
        return
    h = _fresh_handler()
    results = list(h.handler({
        "id": "t-5",
        "input": {
            "segments": [
                {"text": "Hello.", "voice": "af_heart", "speed": 1.0},
                {"text": "Hi there.", "voice": "am_michael", "speed": 1.0},
            ],
            "output_format": "wav",
        },
    }))
    final = [r for r in results if "audio_b64" in r]
    assert final, f"Expected audio result, got: {results}"
    assert final[0]["sample_rate"] == 24000


def test_handler_seed_is_applied():
    """Setting seed calls torch.manual_seed before generation."""
    if torch is None:
        return
    h = _fresh_handler()
    with patch("handler.torch.manual_seed") as mock_seed:
        list(h.handler({"id": "t-6", "input": {"text": "Hi.", "seed": 99, "output_format": "wav"}}))
    mock_seed.assert_called_once_with(99)


def test_handler_oom_yields_oom_error():
    if torch is None:
        return
    h = _fresh_handler()
    mock_pipeline = MagicMock()
    mock_pipeline.__call__ = MagicMock(side_effect=torch.cuda.OutOfMemoryError("fake OOM"))

    with patch.object(h, "_get_pipeline", return_value=mock_pipeline):
        results = list(h.handler({"id": "t-7", "input": {"text": "Hello."}}))

    oom = [r for r in results if r.get("error") == "oom"]
    assert oom, f"Expected oom error, got: {results}"


def test_handler_general_exception_returns_error():
    if torch is None:
        return
    h = _fresh_handler()
    mock_pipeline = MagicMock()
    mock_pipeline.__call__ = MagicMock(side_effect=RuntimeError("something broke"))

    with patch.object(h, "_get_pipeline", return_value=mock_pipeline):
        results = list(h.handler({"id": "t-8", "input": {"text": "Hello."}}))

    assert any("error" in r for r in results)


def test_handler_yields_status_events():
    """Handler yields status events before the final result or error."""
    if torch is None:
        return
    h = _fresh_handler()
    mock_pipeline = MagicMock()
    mock_pipeline.__call__ = MagicMock(side_effect=RuntimeError("stopped after status checks"))

    with patch.object(h, "_get_pipeline", return_value=mock_pipeline):
        results = list(h.handler({"id": "t-9", "input": {"text": "Hello."}}))

    statuses = [r.get("status") for r in results if "status" in r]
    assert "loading" in statuses, f"Expected 'loading' status, got: {results}"
    assert "generating" in statuses, f"Expected 'generating' status, got: {results}"


def test_lang_for_voice():
    """_lang_for_voice correctly maps voice prefixes to lang_code."""
    if torch is None:
        return
    h = _fresh_handler()
    assert h._lang_for_voice("af_heart") == "a"
    assert h._lang_for_voice("am_michael") == "a"
    assert h._lang_for_voice("bf_emma") == "b"
    assert h._lang_for_voice("bm_george") == "b"
    assert h._lang_for_voice("unknown_voice") == "a"  # default
