"""
Base Tool class for Claudeway agents.

Tools allow agents to interact with external systems and capabilities.
"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    Base class for all tools that agents can use.

    Tools extend agent capabilities by providing structured interfaces
    to external systems, APIs, or platform features.
    """

    name: str = "base_tool"
    description: str = "Base tool class"
    input_schema: dict[str, Any] = {}

    @abstractmethod
    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Execute the tool with the given parameters.

        Returns:
            A dictionary with the tool execution result.
            Should include "success" boolean and either "result" or "error".
        """
        pass

    def get_schema(self) -> dict[str, Any]:
        """
        Get the tool schema for use in Claude API calls.

        Returns a tool definition compatible with Anthropic's tool use format.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def format_for_claude(self) -> str:
        """
        Format this tool for inclusion in a Claude system prompt.

        Returns a description of what this tool does and how to use it.
        """
        return f"""
Tool: {self.name}

{self.description}

Parameters:
{self._format_parameters()}
"""

    def _format_parameters(self) -> str:
        """Format the input schema for human reading."""
        if not self.input_schema.get("properties"):
            return "  No parameters"

        lines = []
        for name, schema in self.input_schema["properties"].items():
            required = name in self.input_schema.get("required", [])
            req_marker = " (required)" if required else " (optional)"
            desc = schema.get("description", "")
            lines.append(f"  - {name}: {desc}{req_marker}")

        return "\n".join(lines)
