"""Deterministic stand-in for AnthropicLLMProvider -- zero cost, no network,
no ANTHROPIC_API_KEY required. Used in pytest (dependency override) and in
local dev via LLM_PROVIDER_MODE=fake so the full ingest -> profile ->
description pipeline is exercisable offline."""

from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.model_interpretation_schema import KeyDriver, ModelInterpretationResult
from app.services.llm.modeling_spec_schema import ChatTurnResponse, ModelingSpecFields
from app.services.llm.provider import LLMResult, StructuredLLMResult, ToolLoopResult

CANNED_DESCRIPTION = (
    "[Fake description -- LLM_PROVIDER_MODE=fake] This dataset was profiled "
    "successfully. Enable a real Anthropic API key and set "
    "LLM_PROVIDER_MODE=live to generate a real description."
)

CANNED_REPLY = (
    "[Fake reply -- LLM_PROVIDER_MODE=fake] Set LLM_PROVIDER_MODE=live and a "
    "real ANTHROPIC_API_KEY for a real conversation."
)

CANNED_INTERPRETATION = ModelInterpretationResult(
    summary_text=(
        "[Fake interpretation -- LLM_PROVIDER_MODE=fake] Set LLM_PROVIDER_MODE=live "
        "and a real ANTHROPIC_API_KEY for a real interpretation."
    ),
    key_drivers=[
        KeyDriver(feature="placeholder_feature", plain_description="Fake driver for offline testing.", relative_importance=1.0),
    ],
)

DEFAULT_FAKE_SPEC = ModelingSpecFields(
    task_type="classification",
    task_description="Fake modeling spec for offline testing",
    target="",
    candidate_features=[],
    evaluation_metric="accuracy",
    retrain_cadence="weekly",
    score_cadence="daily",
)


class FakeLLMProvider:
    async def complete(
        self,
        *,
        db: AsyncSession,
        task_type: str,
        organization_id: str,
        prompt: str,
        system: str | None = None,
        trigger: str | None = None,
        related_table: str | None = None,
        related_id: str | None = None,
        max_tokens: int = 1024,
    ) -> LLMResult:
        return LLMResult(
            text=CANNED_DESCRIPTION,
            model_id="fake-model",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=Decimal("0"),
            stop_reason="end_turn",
            request_id=None,
        )

    async def complete_structured(
        self,
        *,
        db: AsyncSession,
        task_type: str,
        organization_id: str,
        messages: list[dict],
        output_format: type[BaseModel],
        system: str | None = None,
        trigger: str | None = None,
        related_table: str | None = None,
        related_id: str | None = None,
        max_tokens: int = 2048,
    ) -> StructuredLLMResult:
        parsed: BaseModel
        if output_format is ChatTurnResponse:
            parsed = ChatTurnResponse(
                reply_message=CANNED_REPLY,
                modeling_spec=_carry_forward_spec(messages),
            )
        elif output_format is ModelInterpretationResult:
            parsed = CANNED_INTERPRETATION
        else:
            parsed = output_format.model_construct()

        return StructuredLLMResult(
            parsed=parsed,
            model_id="fake-model",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=Decimal("0"),
            stop_reason="end_turn",
            request_id=None,
        )

    async def run_tool_loop(
        self,
        *,
        db: AsyncSession,
        task_type: str,
        organization_id: str,
        messages: list[dict],
        tools: list,
        system: str,
        trigger: str | None = None,
        related_table: str | None = None,
        related_id: str | None = None,
        max_tokens: int = 8192,
    ) -> ToolLoopResult:
        # No real tool calls in fake mode -- just echo a canned reply and
        # append it to history, so the surrounding plumbing (persistence,
        # response shape) is still exercisable offline.
        history = [*messages, {"role": "assistant", "content": [{"type": "text", "text": CANNED_REPLY}]}]
        return ToolLoopResult(
            reply_text=CANNED_REPLY,
            raw_messages=history,
            model_id="fake-model",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=Decimal("0"),
        )


def _carry_forward_spec(messages: list[dict]) -> ModelingSpecFields:
    """Offline stand-in for real spec continuity: reuse the most recent
    assistant turn's spec (if any) instead of always resetting to the
    default, so the fake provider still exercises "carry state forward"."""
    for m in reversed(messages):
        if m.get("role") == "assistant":
            try:
                prior = ChatTurnResponse.model_validate_json(m["content"])
            except Exception:
                continue
            if prior.modeling_spec is not None:
                return prior.modeling_spec
    return DEFAULT_FAKE_SPEC
