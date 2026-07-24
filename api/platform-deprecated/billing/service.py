"""
Billing Service

Business logic for usage tracking and billing.
"""

from datetime import datetime, timedelta
from uuid import uuid4
from typing import Optional

from sqlalchemy import select, func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models import UsageRecord, Invoice, InvoiceStatus


# Pricing (in cents per unit)
PRICING = {
    "free": {
        "messages": 0,  # Free tier gets free usage up to limit
        "tokens": 0,
    },
    "pro": {
        "messages": 0.01,  # $0.01 per message over limit
        "tokens": 0.0002,  # $0.0002 per token
    },
    "enterprise": {
        "messages": 0.005,  # Volume discount
        "tokens": 0.0001,
    },
}


class BillingService:
    """Service for billing and usage tracking."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_usage(
        self,
        tenant_id: str,
        agent_id: str,
        messages: int = 0,
        tokens: int = 0,
        duration_seconds: int = 0,
    ) -> UsageRecord:
        """Record usage for billing."""
        record = UsageRecord(
            id=str(uuid4()),
            tenant_id=tenant_id,
            agent_id=agent_id,
            messages=messages,
            tokens=tokens,
            duration_seconds=duration_seconds,
        )

        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        return record

    async def get_usage(
        self,
        tenant_id: str,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> dict:
        """Get usage stats for a tenant."""
        if not period_start:
            period_start = datetime.utcnow().replace(day=1)  # Start of month
        if not period_end:
            period_end = datetime.utcnow()

        # Get usage records
        result = await self.db.execute(
            select(sql_func.sum(UsageRecord.messages), sql_func.sum(UsageRecord.tokens))
            .where(UsageRecord.tenant_id == tenant_id)
            .where(UsageRecord.recorded_at >= period_start)
            .where(UsageRecord.recorded_at <= period_end)
        )

        messages, tokens = result.one()

        return {
            "tenant_id": tenant_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "messages": messages or 0,
            "tokens": tokens or 0,
        }

    async def create_invoice(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Invoice:
        """Create an invoice for a billing period."""
        # Get tenant for pricing tier
        from tenants.models import Tenant

        tenant_result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        # Calculate usage
        usage = await self.get_usage(tenant_id, period_start, period_end)

        # Calculate amount based on tier
        tier_pricing = PRICING.get(tenant.tier, PRICING["pro"])

        # Apply free tier limits
        from tenants.models import TenantTier

        if tenant.tier == TenantTier.FREE:
            messages_charge = max(0, usage["messages"] - tenant.max_messages_per_month) * tier_pricing["messages"]
            tokens_charge = usage["tokens"] * tier_pricing["tokens"]
        else:
            messages_charge = usage["messages"] * tier_pricing["messages"]
            tokens_charge = usage["tokens"] * tier_pricing["tokens"]

        total_amount = messages_charge + tokens_charge

        # Generate invoice number
        invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m')}-{tenant_id[:8]}"

        invoice = Invoice(
            id=str(uuid4()),
            tenant_id=tenant_id,
            invoice_number=invoice_number,
            amount=total_amount,
            period_start=period_start,
            period_end=period_end,
            status=InvoiceStatus.PENDING if total_amount > 0 else InvoiceStatus.PAID,
        )

        self.db.add(invoice)
        await self.db.commit()
        await self.db.refresh(invoice)

        return invoice

    async def list_invoices(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Invoice]:
        """List invoices for a tenant."""
        result = await self.db.execute(
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Get invoice by ID."""
        result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        return result.scalar_one_or_none()
