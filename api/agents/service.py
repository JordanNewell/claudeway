"""
Agent Service (DEPRECATED - Use OrchestrationService instead)

This service uses the old Claude-Flow client.
New code should use api.orchestration.OrchestrationService instead.
"""

from json import dumps as json_dumps
from uuid import uuid4
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Use new naming (backwards compatible)
from agents.deployment import SwarmDeployment as Agent, DeploymentStatus as AgentStatus
from gateway.client import ClaudeFlowClient
from tenants.service import TenantService


class AgentService:
    """Service for managing agents."""

    def __init__(self, db: AsyncSession, claude_flow: ClaudeFlowClient) -> None:
        self.db = db
        self.claude_flow = claude_flow
        self.tenant_service = TenantService(db)

    async def deploy_agent(
        self,
        tenant_id: str,
        name: str,
        template_id: str,
        config: dict,
    ) -> Agent:
        """Deploy a new agent via Claude-Flow."""
        # Check if tenant can deploy more agents
        can_deploy = await self.tenant_service.can_deploy_agent(tenant_id)
        if not can_deploy:
            raise ValueError(f"Tenant {tenant_id} has reached agent limit")

        # Load template configuration
        from templates.service import TemplateService
        template_service = TemplateService(self.db)
        template = await template_service.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        # Merge template config with user config
        swarm_config = {
            **template.config,
            **config,
            "name": f"{tenant_id}-{name}",
        }

        # Create agent record
        agent = Agent(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=name,
            template_id=template_id,
            config=json_dumps(config),
            status=AgentStatus.DEPLOYING,
        )

        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)

        # Deploy to Claude-Flow
        try:
            swarm_result = await self.claude_flow.deploy_swarm(
                config=swarm_config,
                tenant_id=tenant_id,
            )
            agent.swarm_id = swarm_result["swarm_id"]
            agent.status = AgentStatus.RUNNING
            await self.db.commit()
            await self.db.refresh(agent)
        except Exception as e:
            agent.status = AgentStatus.ERROR
            agent.error_message = str(e)
            await self.db.commit()
            await self.db.refresh(agent)
            raise

        return agent

    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def list_agents(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Agent]:
        """List agents with optional filters."""
        query = select(Agent)

        if tenant_id:
            query = query.where(Agent.tenant_id == tenant_id)
        if status:
            query = query.where(Agent.status == status)

        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def stop_agent(self, agent_id: str) -> Agent:
        """Stop a running agent."""
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.swarm_id:
            try:
                await self.claude_flow.stop_swarm(agent.swarm_id)
            except Exception:
                pass  # Continue anyway

        agent.status = AgentStatus.STOPPED
        await self.db.commit()
        await self.db.refresh(agent)

        return agent

    async def delete_agent(self, agent_id: str) -> None:
        """Delete an agent record."""
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Stop if running
        if agent.status == AgentStatus.RUNNING:
            await self.stop_agent(agent_id)

        await self.db.delete(agent)
        await self.db.commit()

    async def send_message(
        self,
        agent_id: str,
        message: str,
        user_id: str | None = None,
    ) -> dict:
        """Send a message to an agent and get response."""
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.status != AgentStatus.RUNNING:
            raise ValueError(f"Agent {agent_id} is not running")

        if not agent.swarm_id:
            raise ValueError(f"Agent {agent_id} has no swarm_id")

        response = await self.claude_flow.send_message_to_swarm(
            swarm_id=agent.swarm_id,
            message=message,
            user_id=user_id,
        )

        # Update last active time
        from datetime import datetime
        agent.last_active_at = datetime.utcnow()
        await self.db.commit()

        # Record usage
        from billing.service import BillingService
        billing_service = BillingService(self.db)
        await billing_service.record_usage(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            messages=1,
            tokens=response.get("tokens", 0),
        )

        return response
