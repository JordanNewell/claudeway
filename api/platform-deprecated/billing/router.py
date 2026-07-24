"""
Billing API Router

REST API endpoints for billing and usage tracking.
"""

# from typing import list (builtin in Python 3.9+)
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from billing.service import BillingService


router = APIRouter()


@router.get("/usage", response_model=dict)
async def get_usage(
    tenant_id: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get usage stats for a tenant."""
    service = BillingService(db)
    return await service.get_usage(tenant_id, period_start, period_end)


@router.get("/invoices", response_model=list[dict])
async def list_invoices(
    tenant_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List invoices for a tenant."""
    service = BillingService(db)
    invoices = await service.list_invoices(tenant_id, limit, offset)
    return [i.to_dict() for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=dict)
async def get_invoice(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get invoice by ID."""
    service = BillingService(db)
    invoice = await service.get_invoice(invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )

    return invoice.to_dict()


@router.post("/invoices/{invoice_id}/pay", response_model=dict)
async def pay_invoice(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark invoice as paid (for testing/manual payment)."""
    from billing.models import InvoiceStatus

    service = BillingService(db)
    invoice = await service.get_invoice(invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )

    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.utcnow()
    await db.commit()

    return invoice.to_dict()


@router.post("/invoices/generate", response_model=dict)
async def generate_invoice(
    tenant_id: str,
    period_start: datetime,
    period_end: datetime,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate an invoice for a billing period."""
    service = BillingService(db)

    try:
        invoice = await service.create_invoice(tenant_id, period_start, period_end)
        return invoice.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
