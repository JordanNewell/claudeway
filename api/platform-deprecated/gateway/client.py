"""
Claude-Flow Gateway Client

Handles communication with Claude-Flow orchestration layer.
This is how Claudeway deploys and manages agents via Claude-Flow.
"""

import httpx
from typing import Any

from config import settings


class ClaudeFlowClient:
    """Client for interacting with Claude-Flow API."""

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ClaudeFlowClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                timeout=30.0,
            )
        return self._client

    async def deploy_swarm(
        self,
        config: dict[str, Any],
        tenant_id: str,
    ) -> dict[str, Any]:
        """
        Deploy a new agent swarm via Claude-Flow.

        Args:
            config: Swarm configuration (topology, agents, consensus, etc.)
            tenant_id: Tenant ID for tagging/multi-tenancy

        Returns:
            Swarm deployment response with swarm_id
        """
        response = await self.client.post(
            "/api/v1/swarms",
            json={
                **config,
                "metadata": {
                    "tenant_id": tenant_id,
                    "deployed_by": "claudeway",
                },
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_swarm_status(self, swarm_id: str) -> dict[str, Any]:
        """Get status of a deployed swarm."""
        response = await self.client.get(f"/api/v1/swarms/{swarm_id}")
        response.raise_for_status()
        return response.json()

    async def stop_swarm(self, swarm_id: str) -> dict[str, Any]:
        """Stop a running swarm."""
        response = await self.client.post(f"/api/v1/swarms/{swarm_id}/stop")
        response.raise_for_status()
        return response.json()

    async def list_swarms(self, tenant_id: str) -> list[dict[str, Any]]:
        """List all swarms for a tenant."""
        response = await self.client.get(
            "/api/v1/swarms",
            params={"tenant_id": tenant_id},
        )
        response.raise_for_status()
        return response.json()

    async def send_message_to_swarm(
        self,
        swarm_id: str,
        message: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to a swarm and get response."""
        response = await self.client.post(
            f"/api/v1/swarms/{swarm_id}/message",
            json={
                "content": message,
                "user_id": user_id,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_swarm_metrics(self, swarm_id: str) -> dict[str, Any]:
        """Get metrics for a swarm (messages, tokens, etc.)."""
        response = await self.client.get(f"/api/v1/swarms/{swarm_id}/metrics")
        response.raise_for_status()
        return response.json()
