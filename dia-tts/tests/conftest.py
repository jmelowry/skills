"""
Pytest configuration: mock GPU-only packages so all tests run on CPU in CI.

This file is loaded by pytest before any test module, so the mocks are in place
before `import handler` triggers `runpod.serverless.start(...)`.
"""
import sys
from unittest.mock import MagicMock

# Prevent runpod.serverless.start() from connecting to RunPod infrastructure
if "runpod" not in sys.modules:
    sys.modules["runpod"] = MagicMock()

# dia2 is GPU-only and can't be installed in CPU CI
if "dia2" not in sys.modules:
    sys.modules["dia2"] = MagicMock()
