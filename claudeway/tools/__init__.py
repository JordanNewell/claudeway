"""
Claudeway Tools - Extend agent capabilities.

Tools allow Claude agents to interact with external systems and platform
features. Two flavors: Python callables (subclass Tool) and MCP server tools
(via MCPClient). Both present the same execute()/get_schema() shape to agents.
"""

from .base import Tool
from .claudeway import ClaudewayTool, create_claudeway_tool

__all__ = [
    "Tool",
    "ClaudewayTool",
    "create_claudeway_tool",
    "MCPTool",
    "MCPClient",
]


def __getattr__(name: str):
    # Lazy-load MCP symbols so the (optional) mcp dep isn't required at import.
    if name in ("MCPTool", "MCPClient"):
        from . import mcp as _mcp
        return getattr(_mcp, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
