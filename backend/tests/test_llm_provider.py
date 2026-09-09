from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.llm_usage_log import LlmUsageLog
from app.services.llm.cost_guard import SpendCapExceededError
from app.services.llm.modeling_spec_schema import ChatTurnResponse, ModelingSpecFields
from app.services.llm.provider import AnthropicLLMProvider, RefusalError


def _fake_response(text: str = "A generated description.", stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=120, output_tokens=40),
        stop_reason=stop_reason,
        stop_details=None,
        _request_id="req_test123",
    )


def _fake_parsed_response(parsed_output, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        parsed_output=parsed_output,
        usage=SimpleNamespace(input_tokens=200, output_tokens=80),
        stop_reason=stop_reason,
        stop_details=None,
        _request_id="req_test456",
    )


async def test_complete_logs_usage_and_returns_result(db_session, default_org_id):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response()
    provider = AnthropicLLMProvider(client=fake_client)

    result = await provider.complete(
        db=db_session,
        task_type="dataset_description",
        organization_id=default_org_id,
        prompt="describe this dataset",
    )

    assert result.text == "A generated description."
    assert result.model_id == "claude-opus-5"  # falls back to DEFAULT_LLM_MODEL
    assert result.input_tokens == 120
    assert result.output_tokens == 40
    assert result.cost_estimate_usd == Decimal("120") / Decimal("1000000") * Decimal(
        "5.00"
    ) + Decimal("40") / Decimal("1000000") * Decimal("25.00")

    logged = (
        await db_session.execute(
            select(LlmUsageLog).where(LlmUsageLog.organization_id == default_org_id)
        )
    ).scalar_one()
    assert logged.model_id == "claude-opus-5"
    assert logged.input_tokens == 120
    assert logged.stop_reason == "end_turn"


async def test_complete_calls_thinking_and_effort_correctly(db_session, default_org_id):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response()
    provider = AnthropicLLMProvider(client=fake_client)

    await provider.complete(
        db=db_session,
        task_type="dataset_description",
        organization_id=default_org_id,
        prompt="describe this dataset",
    )

    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "medium"}


async def test_over_budget_prevents_call(db_session, default_org_id):
    db_session.add(
        LlmUsageLog(
            organization_id=default_org_id,
            task_type="dataset_description",
            model_id="claude-opus-5",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=Decimal("999.00"),
            stop_reason="end_turn",
        )
    )
    await db_session.commit()

    fake_client = MagicMock()
    provider = AnthropicLLMProvider(client=fake_client)

    with pytest.raises(SpendCapExceededError):
        await provider.complete(
            db=db_session,
            task_type="dataset_description",
            organization_id=default_org_id,
            prompt="describe this dataset",
        )

    fake_client.messages.create.assert_not_called()


async def test_refusal_logs_and_raises(db_session, default_org_id):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response(
        text="", stop_reason="refusal"
    )
    provider = AnthropicLLMProvider(client=fake_client)

    with pytest.raises(RefusalError):
        await provider.complete(
            db=db_session,
            task_type="dataset_description",
            organization_id=default_org_id,
            prompt="describe this dataset",
        )

    logged = (
        await db_session.execute(
            select(LlmUsageLog).where(LlmUsageLog.organization_id == default_org_id)
        )
    ).scalar_one()
    assert logged.stop_reason == "refusal"


def _sample_chat_turn() -> ChatTurnResponse:
    return ChatTurnResponse(
        reply_message="Got it, here's a proposed spec.",
        modeling_spec=ModelingSpecFields(
            task_type="risk_scoring",
            task_description="30-day outbreak probability",
            target="outbreak_within_30d",
            candidate_features=["vaccination_rate_mmr", "case_count_30d"],
            evaluation_metric="AUC-ROC",
            retrain_cadence="weekly",
            score_cadence="daily",
        ),
    )


async def test_complete_structured_logs_usage_and_returns_parsed(db_session, default_org_id):
    fake_client = MagicMock()
    turn = _sample_chat_turn()
    fake_client.messages.parse.return_value = _fake_parsed_response(turn)
    provider = AnthropicLLMProvider(client=fake_client)

    result = await provider.complete_structured(
        db=db_session,
        task_type="intent_chat",
        organization_id=default_org_id,
        messages=[{"role": "user", "content": "score measles risk"}],
        output_format=ChatTurnResponse,
    )

    assert result.parsed == turn
    assert result.model_id == "claude-opus-5"
    assert result.input_tokens == 200
    assert result.output_tokens == 80

    logged = (
        await db_session.execute(
            select(LlmUsageLog).where(
                LlmUsageLog.organization_id == default_org_id,
                LlmUsageLog.task_type == "intent_chat",
            )
        )
    ).scalar_one()
    assert logged.model_id == "claude-opus-5"


async def test_complete_structured_passes_schema_and_messages(db_session, default_org_id):
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = _fake_parsed_response(_sample_chat_turn())
    provider = AnthropicLLMProvider(client=fake_client)

    messages = [{"role": "user", "content": "hello"}]
    await provider.complete_structured(
        db=db_session,
        task_type="intent_chat",
        organization_id=default_org_id,
        messages=messages,
        output_format=ChatTurnResponse,
        system="be helpful",
    )

    _, kwargs = fake_client.messages.parse.call_args
    assert kwargs["output_format"] is ChatTurnResponse
    assert kwargs["messages"] == messages
    assert kwargs["system"] == "be helpful"


async def test_complete_structured_over_budget_prevents_call(db_session, default_org_id):
    db_session.add(
        LlmUsageLog(
            organization_id=default_org_id,
            task_type="intent_chat",
            model_id="claude-opus-5",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=Decimal("999.00"),
            stop_reason="end_turn",
        )
    )
    await db_session.commit()

    fake_client = MagicMock()
    provider = AnthropicLLMProvider(client=fake_client)

    with pytest.raises(SpendCapExceededError):
        await provider.complete_structured(
            db=db_session,
            task_type="intent_chat",
            organization_id=default_org_id,
            messages=[{"role": "user", "content": "hi"}],
            output_format=ChatTurnResponse,
        )

    fake_client.messages.parse.assert_not_called()
