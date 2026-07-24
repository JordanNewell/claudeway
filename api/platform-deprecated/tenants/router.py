"""
Tenant API Router

REST API endpoints for tenant management.
"""

# from typing import list (builtin in Python 3.9+)
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from tenants.models import Tenant, TenantTier
from tenants.service import TenantService


router = APIRouter()


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    name: str,
    email: str,
    tier: TenantTier = TenantTier.FREE,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new tenant."""
    service = TenantService(db)

    try:
        tenant = await service.create_tenant(name=name, email=email, tier=tier)
        return tenant.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=list[dict])
async def list_tenants(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all tenants."""
    service = TenantService(db)
    tenants = await service.list_tenants(limit=limit, offset=offset)
    return [t.to_dict() for t in tenants]


@router.get("/{tenant_id}", response_model=dict)
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get tenant by ID."""
    service = TenantService(db)
    tenant = await service.get_tenant(tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    return tenant.to_dict()


@router.put("/{tenant_id}/tier", response_model=dict)
async def update_tenant_tier(
    tenant_id: str,
    tier: TenantTier,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update tenant subscription tier."""
    service = TenantService(db)

    try:
        tenant = await service.update_tenant_tier(tenant_id, tier)
        return tenant.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{tenant_id}/suspend", response_model=dict)
async def suspend_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Suspend a tenant."""
    service = TenantService(db)

    try:
        tenant = await service.suspend_tenant(tenant_id)
        return tenant.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
