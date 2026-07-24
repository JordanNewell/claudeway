"""
Tenant Service

Business logic for tenant management.
"""

from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.models import Tenant, TenantTier, TenantStatus


class TenantService:
    """Service for managing tenants."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_tenant(
        self,
        name: str,
        email: str,
        tier: TenantTier = TenantTier.FREE,
    ) -> Tenant:
        """Create a new tenant."""
        # Check if email already exists
        result = await self.db.execute(
            select(Tenant).where(Tenant.email == email)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Tenant with email {email} already exists")

        # Set tier-based limits
        max_agents = {
            TenantTier.FREE: 1,
            TenantTier.PRO: 10,
            TenantTier.ENTERPRISE: -1,  # unlimited
        }[tier]

        max_messages = {
            TenantTier.FREE: 1000,
            TenantTier.PRO: 50000,
            TenantTier.ENTERPRISE: -1,  # unlimited
        }[tier]

        tenant = Tenant(
            id=str(uuid4()),
            name=name,
            email=email,
            tier=tier,
            status=TenantStatus.ACTIVE,
            max_agents=max_agents,
            max_messages_per_month=max_messages,
        )

        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)

        return tenant

    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID."""
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_tenant_by_email(self, email: str) -> Optional[Tenant]:
        """Get tenant by email."""
        result = await self.db.execute(
            select(Tenant).where(Tenant.email == email)
        )
        return result.scalar_one_or_none()

    async def list_tenants(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tenant]:
        """List all tenants."""
        result = await self.db.execute(
            select(Tenant).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def update_tenant_tier(
        self,
        tenant_id: str,
        tier: TenantTier,
    ) -> Tenant:
        """Update tenant subscription tier."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        # Update limits
        max_agents = {
            TenantTier.FREE: 1,
            TenantTier.PRO: 10,
            TenantTier.ENTERPRISE: -1,
        }[tier]

        max_messages = {
            TenantTier.FREE: 1000,
            TenantTier.PRO: 50000,
            TenantTier.ENTERPRISE: -1,
        }[tier]

        tenant.tier = tier
        tenant.max_agents = max_agents
        tenant.max_messages_per_month = max_messages

        await self.db.commit()
        await self.db.refresh(tenant)

        return tenant

    async def suspend_tenant(self, tenant_id: str) -> Tenant:
        """Suspend a tenant."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        tenant.status = TenantStatus.SUSPENDED
        await self.db.commit()
        await self.db.refresh(tenant)

        return tenant

    async def can_deploy_agent(self, tenant_id: str) -> bool:
        """Check if tenant can deploy another agent."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant or tenant.status != TenantStatus.ACTIVE:
            return False

        if tenant.max_agents == -1:  # unlimited
            return True

        # Count current swarm deployments
        from agents.deployment import SwarmDeployment as Agent

        result = await self.db.execute(
            select(Agent).where(
                Agent.tenant_id == tenant_id,
                Agent.status == "running",
            )
        )
        current_count = len(result.scalars().all())

        return current_count < tenant.max_agents
