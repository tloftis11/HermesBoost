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


class ToolLoopResult(BaseModel):
    """The outcome of a full agentic tool-use turn -- may have taken
    several internal round-trips (tool calls, pause_turn restarts). The
    caller must persist `raw_messages` verbatim (it includes every
    tool_use/tool_result block) to correctly resume the conversation next
    turn -- a flattened display string is not enough."""

    model_config = {"arbitrary_types_allowed": True}

    reply_text: str
    raw_messages: list[dict]
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: Decimal


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
    ) -> ToolLoopResult: ...


class RefusalError(Exception):
    def __init__(self, category: str | None, explanation: str | None):
        self.category = category
        self.explanation = explanation
        super().__init__(f"Claude refused the request (category={category}): {explanation}")


MAX_PAUSE_RESTARTS = 5  # bug-guard against a genuine infinite pause_turn loop, not a cost budget


class AnthropicLLMProvider:
    def __init__(self, client: anthropic.Anthropic, async_client: "anthropic.AsyncAnthropic | None" = None):
        self._client = client
        # run_tool_loop needs the async client -- the custom tools it runs
        # (file download, DB writes) are async, and the tool runner drives
        # them on the running event loop rather than blocking it like the
        # sync client's calls do elsewhere in this class.
        self._async_client = async_client or anthropic.AsyncAnthropic()

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
        model_id = await model_config.get_model_for_task(task_type, db)

        await cost_guard.check_budget(organization_id, db)

        history = list(messages)
        total_input_tokens = 0
        total_output_tokens = 0
        last_message = None
        last_stop_reason: str | None = None
        restarts = 0

        # Server-side tools (web_search/web_fetch) run their own internal
        # sampling loop and can stop with stop_reason "pause_turn" after
        # 10 iterations. The tool runner does not auto-resume this (as of
        # anthropic 1.x) -- restart with the paused turn already appended
        # to history, exactly as documented. MAX_PAUSE_RESTARTS bounds a
        # genuine infinite-loop bug, not day-to-day usage.
        while True:
            runner = self._async_client.beta.messages.tool_runner(
                model=model_id,
                max_tokens=max_tokens,
                tools=tools,
                system=system,
                messages=history,
            )
            async for message in runner:
                last_message = message
                total_input_tokens += message.usage.input_tokens
                total_output_tokens += message.usage.output_tokens
                history.append({"role": "assistant", "content": _serialize_blocks(message.content)})
                tool_response = await runner.generate_tool_call_response()
                if tool_response is not None:
                    history.append(tool_response)

            last_stop_reason = last_message.stop_reason if last_message else None
            if last_stop_reason != "pause_turn":
                break
            restarts += 1
            if restarts > MAX_PAUSE_RESTARTS:
                raise RuntimeError("Tool loop gave up after too many pause_turn restarts")

        reply_text = ""
        if last_message is not None:
            reply_text = next((b.text for b in last_message.content if b.type == "text"), "")

        cost_estimate = model_config.estimate_cost_usd(model_id, total_input_tokens, total_output_tokens)

        await usage_logger.log_call(
            db,
            organization_id=organization_id,
            task_type=task_type,
            model_id=model_id,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_estimate_usd=cost_estimate,
            stop_reason=last_stop_reason or "end_turn",
            trigger=trigger,
            request_id=None,
            related_table=related_table,
            related_id=related_id,
        )

        return ToolLoopResult(
            reply_text=reply_text,
            raw_messages=history,
            model_id=model_id,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_estimate_usd=cost_estimate,
        )


def _serialize_blocks(content) -> list[dict]:
    """Assistant-turn content blocks are typed Pydantic response objects,
    not plain dicts -- convert them before storing in a JSONB column or
    replaying them across a later, separate request."""
    return [block.model_dump(mode="json") if hasattr(block, "model_dump") else block for block in content]


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
