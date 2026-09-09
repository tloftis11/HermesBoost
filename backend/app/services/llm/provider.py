"""The single shared LLM entry point.

Every LLM call anywhere in this codebase goes through get_llm_provider() --
never `import anthropic` directly at a call site. This exists specifically
to avoid the pattern seen in prior Claude-integration work where each call
site built its own client instance: here there is exactly one place
anthropic.Anthropic() is ever constructed.

Note vs. the original interface sketch: a `db` parameter was added to
`complete()` -- model routing, the spend-cap check, and usage logging all
need a database session, so the interface can't omit it and still do those
things.
"""

from decimal import Decimal
from typing import Protocol

import anthropic
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.llm import cost_guard, model_config, usage_logger


class LLMResult(BaseModel):
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: Decimal
    stop_reason: str
    request_id: str | None = None


class StructuredLLMResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    parsed: BaseModel
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: Decimal
    stop_reason: str
    request_id: str | None = None


class LLMProvider(Protocol):
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
    ) -> LLMResult: ...

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
    ) -> StructuredLLMResult: ...


class RefusalError(Exception):
    def __init__(self, category: str | None, explanation: str | None):
        self.category = category
        self.explanation = explanation
        super().__init__(f"Claude refused the request (category={category}): {explanation}")


class AnthropicLLMProvider:
    def __init__(self, client: anthropic.Anthropic):
        self._client = client

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
        model_id = await model_config.get_model_for_task(task_type, db)

        # Cost guard runs before any Anthropic call -- never after.
        await cost_guard.check_budget(organization_id, db)

        kwargs: dict = {
            "model": model_id,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)

        stop_reason = response.stop_reason
        if stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            explanation = getattr(response.stop_details, "explanation", None) if response.stop_details else None
            text = ""
        else:
            text = next((b.text for b in response.content if b.type == "text"), "")

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_estimate = model_config.estimate_cost_usd(model_id, input_tokens, output_tokens)

        # Always log -- even on refusal -- so the ledger stays accurate.
        await usage_logger.log_call(
            db,
            organization_id=organization_id,
            task_type=task_type,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost_estimate,
            stop_reason=stop_reason,
            trigger=trigger,
            request_id=response._request_id,
            related_table=related_table,
            related_id=related_id,
        )

        if stop_reason == "refusal":
            raise RefusalError(category, explanation)

        return LLMResult(
            text=text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost_estimate,
            stop_reason=stop_reason,
            request_id=response._request_id,
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
        model_id = await model_config.get_model_for_task(task_type, db)

        await cost_guard.check_budget(organization_id, db)

        kwargs: dict = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": messages,
            "output_format": output_format,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.parse(**kwargs)

        stop_reason = response.stop_reason
        parsed = None if stop_reason == "refusal" else response.parsed_output
        if stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            explanation = getattr(response.stop_details, "explanation", None) if response.stop_details else None

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_estimate = model_config.estimate_cost_usd(model_id, input_tokens, output_tokens)

        await usage_logger.log_call(
            db,
            organization_id=organization_id,
            task_type=task_type,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost_estimate,
            stop_reason=stop_reason,
            trigger=trigger,
            request_id=response._request_id,
            related_table=related_table,
            related_id=related_id,
        )

        if stop_reason == "refusal":
            raise RefusalError(category, explanation)

        return StructuredLLMResult(
            parsed=parsed,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost_estimate,
            stop_reason=stop_reason,
            request_id=response._request_id,
        )


_client: anthropic.Anthropic | None = None
_provider: "LLMProvider | None" = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.LLM_PROVIDER_MODE == "fake":
            from app.services.llm.fake_provider import FakeLLMProvider

            _provider = FakeLLMProvider()
        else:
            _provider = AnthropicLLMProvider(client=_get_client())
    return _provider


def reset_provider_for_tests() -> None:
    """Test-only hook: clears the memoized singleton so tests can swap providers."""
    global _provider, _client
    _provider = None
    _client = None
