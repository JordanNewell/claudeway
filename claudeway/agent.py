"""
Claudeway Agent - A Claude agent that can think and act.

Built on Anthropic's Agent SDK with clean abstractions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic


@dataclass
class Message:
    """A message in an agent conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)

    def to_api_format(self) -> dict[str, Any]:
        """Convert to Anthropic API format."""
        result = {"role": self.role, "content": self.content}

        # Add tool calls if present (for assistant messages)
        if self.tool_calls:
            # Convert content to blocks format
            result["content"] = [{"type": "text", "text": self.content}]
            for call in self.tool_calls:
                result["content"].append({
                    "type": "tool_use",
                    "id": call.get("id", ""),
                    "name": call.get("name", ""),
                    "input": call.get("input", {})
                })

        # Add tool results if present (for user messages after tool use)
        if self.tool_results:
            if isinstance(result["content"], str):
                result["content"] = [{"type": "text", "text": self.content}]

            for tool_result in self.tool_results:
                result["content"].append({
                    "type": "tool_result",
                    "tool_use_id": tool_result.get("tool_use_id", ""),
                    "content": str(tool_result.get("result", ""))
                })

        return result


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    role: str
    instructions: str
    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[Any] = field(default_factory=list)  # List of Tool instances


class Agent:
    """
    A Claude agent - can reason, use tools, and collaborate.

    Minimal implementation. No unnecessary abstractions.
    """

    def __init__(self, config: AgentConfig, api_key: str | None = None) -> None:
        self.config = config
        self.client = AsyncAnthropic(api_key=api_key)
        self.messages: list[Message] = []
        self.available_tools = {tool.name: tool for tool in config.tools}

    async def think(self, input_message: str) -> str:
        """
        Process an input and generate a response.

        Core thinking loop - uses Claude to reason about the input.
        Handles tool use automatically if Claude requests it.
        """
        # Add user message to history
        self.messages.append(Message(role="user", content=input_message))

        # Build API messages
        api_messages = self._build_api_messages()

        # Get system prompt
        system_prompt = self._build_system_prompt()

        # Prepare tools for Claude API. Real Anthropic API rejects tools=None
        # (the GLM proxy was lenient about it) — only include the kwarg when
        # there are tools.
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "system": system_prompt,
            "messages": api_messages,
        }
        if self.config.tools:
            kwargs["tools"] = [tool.get_schema() for tool in self.config.tools]

        # Call Claude
        response = await self.client.messages.create(**kwargs)

        # Process response (may contain tool use)
        return await self._process_response(response)

    async def _process_response(self, response) -> str:
        """Process Claude response, handling tool use if present."""
        content_blocks = response.content

        # Extract text and tool calls
        text_content = []
        tool_calls = []

        for block in content_blocks:
            if block.type == "text":
                text_content.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })

        # Create assistant message
        assistant_text = "\n".join(text_content)
        assistant_message = Message(role="assistant", content=assistant_text, tool_calls=tool_calls)
        self.messages.append(assistant_message)

        # If there are tool calls, execute them and continue
        if tool_calls:
            return await self._execute_tool_calls(tool_calls, assistant_message)

        return assistant_text

    async def _execute_tool_calls(self, tool_calls: list[dict], assistant_message: Message) -> str:
        """Execute tool calls and get final response from Claude."""
        tool_results = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"]

            # Find and execute the tool
            if tool_name in self.available_tools:
                tool = self.available_tools[tool_name]
                try:
                    result = await tool.execute(**tool_input)
                    tool_results.append({
                        "tool_use_id": tool_call["id"],
                        "result": result
                    })
                except Exception as e:
                    tool_results.append({
                        "tool_use_id": tool_call["id"],
                        "result": {"error": str(e)}
                    })
            else:
                tool_results.append({
                    "tool_use_id": tool_call["id"],
                    "result": {"error": f"Tool {tool_name} not found"}
                })

        # Add user message with tool results
        user_message = Message(
            role="user",
            content="",  # Empty text, only tool results
            tool_results=tool_results
        )
        self.messages.append(user_message)

        # Get final response from Claude
        api_messages = self._build_api_messages()
        system_prompt = self._build_system_prompt()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "system": system_prompt,
            "messages": api_messages,
        }
        if self.config.tools:
            kwargs["tools"] = [tool.get_schema() for tool in self.config.tools]

        response = await self.client.messages.create(**kwargs)

        # Process final response (may have more tool calls)
        return await self._process_response(response)

    def _build_api_messages(self) -> list[dict]:
        """Build messages in Anthropic API format."""
        return [msg.to_api_format() for msg in self.messages]

    def _build_system_prompt(self) -> str:
        """Build the system prompt from agent config."""
        prompt = f"""You are {self.config.name}, {self.config.role}.

{self.config.instructions}"""

        # Add tool descriptions if available
        if self.config.tools:
            prompt += "\n\nYou have access to the following tools:\n"
            for tool in self.config.tools:
                prompt += tool.format_for_claude()

        prompt += "\n\nAlways think step by step. Be thorough but concise."

        return prompt

    def reset(self) -> None:
        """Clear conversation history."""
        self.messages = []

    def get_state(self) -> dict[str, Any]:
        """Get agent state for inspection."""
        return {
            "name": self.config.name,
            "role": self.config.role,
            "message_count": len(self.messages),
            "tools_available": list(self.available_tools.keys()),
            "last_message": self.messages[-1].content if self.messages else None,
        }
