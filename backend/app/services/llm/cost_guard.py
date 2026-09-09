"""Spend-cap check, run before every LLM call -- never after."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_usage_log import LlmUsageLog
from app.models.organization import Organization


class SpendCapExceededError(Exception):
    def __init__(self, organization_id: str, spent: Decimal, cap: Decimal):
        self.organization_id = organization_id
        self.spent = spent
        self.cap = cap
        super().__init__(
            f"Organization {organization_id} has spent ${spent} against a "
            f"${cap} monthly LLM budget -- refusing further calls this month."
        )


async def check_budget(organization_id: str, db: AsyncSession) -> None:
    org = await db.get(Organization, organization_id)
    if org is None:
        # Unknown org: fail closed rather than silently allowing spend.
        raise SpendCapExceededError(organization_id, Decimal("0"), Decimal("0"))

    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.coalesce(func.sum(LlmUsageLog.cost_estimate_usd), 0)).where(
            LlmUsageLog.organization_id == organization_id,
            LlmUsageLog.created_at >= month_start,
        )
    )
    spent = Decimal(result.scalar_one())

    if spent >= org.monthly_llm_budget_usd:
        raise SpendCapExceededError(organization_id, spent, org.monthly_llm_budget_usd)
