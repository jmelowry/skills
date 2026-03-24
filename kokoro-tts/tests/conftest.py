"""
Pytest configuration: mock GPU-only packages so all tests run on CPU in CI.

This file is loaded by pytest before any test module, so the mocks are in place
before `import handler` triggers `runpod.serverless.start(...)`.
"""
import sys
from unittest.mock import MagicMock

import numpy as np

# Prevent runpod.serverless.start() from connecting to RunPod infrastructure
if "runpod" not in sys.modules:
    sys.modules["runpod"] = MagicMock()

# Mock kokoro.KPipeline — returns fake audio chunks (numpy float32 zeros)
if "kokoro" not in sys.modules:
    _fake_audio = np.zeros(24000, dtype=np.float32)  # 1 second of silence at 24kHz

    def _fake_pipeline_call(text, voice="af_heart", speed=1.0):
        yield ("graphemes", "phonemes", _fake_audio)

    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.__call__ = MagicMock(side_effect=_fake_pipeline_call)

    MockKPipeline = MagicMock(return_value=mock_pipeline_instance)

    mock_kokoro = MagicMock()
    mock_kokoro.KPipeline = MockKPipeline
    sys.modules["kokoro"] = mock_kokoro
