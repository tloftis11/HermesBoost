from decimal import Decimal

import pytest

from app.models.llm_usage_log import LlmUsageLog
from app.services.llm.cost_guard import SpendCapExceededError, check_budget


async def _log_spend(db_session, org_id: str, cost: Decimal) -> None:
    db_session.add(
        LlmUsageLog(
            organization_id=org_id,
            task_type="dataset_description",
            model_id="claude-opus-5",
            input_tokens=100,
            output_tokens=100,
            cost_estimate_usd=cost,
            stop_reason="end_turn",
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_under_budget_passes(db_session, default_org_id):
    await _log_spend(db_session, default_org_id, Decimal("5.00"))
    await check_budget(default_org_id, db_session)  # should not raise


@pytest.mark.asyncio
async def test_over_budget_raises(db_session, default_org_id):
    # Test org's monthly_llm_budget_usd is seeded at 20.00 (see conftest).
    await _log_spend(db_session, default_org_id, Decimal("25.00"))
    with pytest.raises(SpendCapExceededError):
        await check_budget(default_org_id, db_session)


@pytest.mark.asyncio
async def test_at_cap_exactly_raises(db_session, default_org_id):
    await _log_spend(db_session, default_org_id, Decimal("20.00"))
    with pytest.raises(SpendCapExceededError):
        await check_budget(default_org_id, db_session)


@pytest.mark.asyncio
async def test_unknown_org_fails_closed(db_session):
    with pytest.raises(SpendCapExceededError):
        await check_budget("00000000-0000-0000-0000-000000000000", db_session)
