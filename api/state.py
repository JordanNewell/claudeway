"""
Claudeway State - Shared application state.

Holds the Runtime singleton that manages all agents and swarms.
"""

from typing import Any
from claudeway.runtime import Runtime


# Global runtime instance
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    """Get the global Runtime instance."""
    global _runtime

    if _runtime is None:
        _runtime = Runtime()

    return _runtime


def set_runtime(runtime: Runtime) -> None:
    """Set the global Runtime instance."""
    global _runtime
    _runtime = runtime


def reset_runtime() -> None:
    """Reset the global Runtime instance (for testing)."""
    global _runtime
    _runtime = None
