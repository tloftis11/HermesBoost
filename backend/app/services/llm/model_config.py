"""task_type -> model_id lookup, backed by the llm_task_model_config table.

This is the extension point for the design doc's "swappable model layer"
requirement: adding a new task type or repointing an existing one at a
different model is a config-table change, not a code change.
"""

import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm_task_model_config import LlmTaskModelConfig

# Per-1M-token pricing, USD. Confirmed current as of this milestone; revisit
# when Anthropic updates pricing or new task types route to other models.
PRICE_TABLE: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": (Decimal("2.00"), Decimal("10.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
}

_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[str, float]] = {}


async def get_model_for_task(task_type: str, db: AsyncSession) -> str:
    cached = _cache.get(task_type)
    if cached and (time.monotonic() - cached[1]) < _CACHE_TTL_SECONDS:
        return cached[0]

    result = await db.execute(
        select(LlmTaskModelConfig.model_id).where(LlmTaskModelConfig.task_type == task_type)
    )
    model_id = result.scalar_one_or_none() or settings.DEFAULT_LLM_MODEL
    _cache[task_type] = (model_id, time.monotonic())
    return model_id


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    input_price, output_price = PRICE_TABLE.get(
        model_id, PRICE_TABLE["claude-opus-5"]
    )
    million = Decimal("1000000")
    return (Decimal(input_tokens) / million * input_price) + (
        Decimal(output_tokens) / million * output_price
    )
