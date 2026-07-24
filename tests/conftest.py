"""
Pytest configuration for the Claudeway test suite.

Adds the project root to sys.path so `core` / `api` import without an install,
and enables asyncio mode so async tests run without per-test decorators (we
still mark them explicitly for clarity).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
