"""Writes llm_usage_log rows -- called unconditionally after every LLM call,
including refusals, so the ledger stays accurate regardless of outcome."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_usage_log import LlmUsageLog


async def log_call(
    db: AsyncSession,
    *,
    organization_id: str,
    task_type: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_estimate_usd: Decimal,
    stop_reason: str,
    trigger: str | None = None,
    request_id: str | None = None,
    related_table: str | None = None,
    related_id: str | None = None,
) -> None:
    row = LlmUsageLog(
        organization_id=organization_id,
        task_type=task_type,
        model_id=model_id,
        trigger=trigger,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate_usd=cost_estimate_usd,
        stop_reason=stop_reason,
        request_id=request_id,
        related_table=related_table,
        related_id=related_id,
    )
    db.add(row)
    await db.commit()
