"""
Handler unit tests — run on CPU in CI (no GPU, no real model).

conftest.py mocks runpod and dia2 before any import, so handler.py can be
imported without triggering serverless.start() or loading the model.

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
    """Return a fresh import of handler (clearing cached module state)."""
    if "handler" in sys.modules:
        del sys.modules["handler"]
    import handler as h  # noqa: PLC0415

    return h


if pytest is not None:
    pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")


def test_handler_missing_required_script():
    if torch is None:
        return
    h = _fresh_handler()
    results = list(h.handler({"id": "t-1", "input": {}}))
    assert any("error" in r for r in results), f"Expected error, got: {results}"


def test_handler_invalid_field_type():
    if torch is None:
        return
    h = _fresh_handler()
    results = list(h.handler({"id": "t-2", "input": {"script": "[S1] Hi.", "cfg_scale": "not-a-number"}}))
    assert any("error" in r for r in results)


def test_handler_oom_yields_oom_error():
    if torch is None:
        return
    h = _fresh_handler()
    mock_model = MagicMock()
    mock_model.generate.side_effect = torch.cuda.OutOfMemoryError("fake OOM")

    with patch.object(h, "_get_model", return_value=mock_model):
        results = list(h.handler({"id": "t-3", "input": {"script": "[S1] Hello."}}))

    oom = [r for r in results if r.get("error") == "oom"]
    assert oom, f"Expected oom error, got: {results}"


def test_handler_general_exception_returns_error():
    if torch is None:
        return
    h = _fresh_handler()
    mock_model = MagicMock()
    mock_model.generate.side_effect = RuntimeError("something broke")

    with patch.object(h, "_get_model", return_value=mock_model):
        results = list(h.handler({"id": "t-4", "input": {"script": "[S1] Hello."}}))

    assert any("error" in r for r in results)


def test_handler_yields_status_events():
    """Handler yields status events before the final result or error."""
    if torch is None:
        return
    h = _fresh_handler()
    mock_model = MagicMock()
    # Let generate raise so we don't need to build a real result — statuses come before generate()
    mock_model.generate.side_effect = RuntimeError("stopped after status checks")

    with patch.object(h, "_get_model", return_value=mock_model):
        results = list(h.handler({"id": "t-5", "input": {"script": "[S1] Hello. [S2] Hi."}}))

    statuses = [r.get("status") for r in results if "status" in r]
    assert "loading" in statuses, f"Expected 'loading' status, got: {results}"
    assert "generating" in statuses, f"Expected 'generating' status, got: {results}"
