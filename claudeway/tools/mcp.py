"""
MCP tool adapter - let agents call Model Context Protocol servers.

MCP is the 2026 standard for giving agents tools (Goose, Claude Desktop, and
others all speak it). This adapter lets you hand an MCP server's tools to a
Claudeway Agent exactly like a Python Tool — same execute()/get_schema() shape.

The `mcp` package is an optional dependency. Importing this module without it
installed raises a clear ImportError pointing at `pip install claudeway[mcp]`.
"""

from __future__ import annotations

from typing import Any

from .base import Tool


class MCPTool(Tool):
    """
    Wrap a single MCP server tool as a Claudeway Tool.

    The server connection is owned by the caller (an MCPClient session) and
    passed in; this class only adapts one tool's schema + invocation.
    """

    def __init__(
        self,
        session: Any,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        self._session = session
        self.name = tool_name
        self.description = description or f"MCP tool: {tool_name}"
        self.input_schema = input_schema or {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Call the MCP server tool and normalize the result."""
        result = await self._session.call_tool(self.name, kwargs)
        # MCP returns content blocks; flatten to text for the agent.
        if hasattr(result, "content") and result.content:
            texts = [
                getattr(block, "text", str(block))
                for block in result.content
            ]
            joined = "\n".join(texts)
            return {"success": not getattr(result, "is_error", False), "result": joined}
        return {"success": True, "result": str(result)}


class MCPClient:
    """
    Lazy connection holder for an MCP server.

    Usage:
        async with MCPClient(transport) as mc:
            tools = await mc.tools()  # list[MCPTool] for every server tool
            agent = Agent(AgentConfig(..., tools=tools))

    Kepts the transport open for the agent's lifetime so repeated tool calls
    don't reconnect each time.
    """

    def __init__(self, transport: Any) -> None:
        try:
            from mcp import ClientSession  # noqa: F401
        except ImportError as e:  # pragma: no cover - env-dependent
            raise ImportError(
                "MCP support requires the 'mcp' package. "
                "Install with: pip install claudeway[mcp]"
            ) from e
        self._transport = transport
        self._session: Any = None
        self._cm: Any = None

    async def __aenter__(self) -> MCPClient:
        from mcp import ClientSession
        read, write = self._transport
        self._cm = ClientSession(read, write)
        self._session = await self._cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._cm is not None:
            await self._cm.__aexit__(*exc)
        self._session = None
        self._cm = None

    async def tools(self) -> list[MCPTool]:
        """List the server's tools as Claudeway Tool instances."""
        listing = await self._session.list_tools()
        return [
            MCPTool(
                session=self._session,
                tool_name=t.name,
                description=t.description,
                input_schema=t.inputSchema,
            )
            for t in listing.tools
        ]
