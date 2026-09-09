"""Runs one turn of the data-acquisition assistant's tool-use loop.

Persists both the raw Anthropic-format history (needed to correctly
resume the tool-loop conversation next turn -- includes every
tool_use/tool_result block) and a human-readable projection for the chat
UI, mirroring the split ChatMessage already uses for the modeling-spec
intent chat (raw structured content vs. a display-friendly string)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_acquisition import DataAcquisitionMessage, DataAcquisitionSession
from app.services.llm.data_acquisition_tools import build_tools
from app.services.llm.prompts import DATA_ACQUISITION_SYSTEM_PROMPT
from app.services.llm.provider import get_llm_provider


async def run_data_acquisition_turn(
    db: AsyncSession, organization_id: str, session: DataAcquisitionSession, user_message: str
) -> tuple[str, list[str]]:
    """Returns (reply_text, staged_dataset_ids) for this turn."""
    tools, staged_dataset_ids = build_tools(db, organization_id)

    history = [*session.raw_messages, {"role": "user", "content": user_message}]

    result = await get_llm_provider().run_tool_loop(
        db=db,
        task_type="data_acquisition",
        organization_id=organization_id,
        messages=history,
        tools=tools,
        system=DATA_ACQUISITION_SYSTEM_PROMPT,
        trigger=f"data_acquisition_session:{session.id}",
        related_table="data_acquisition_sessions",
        related_id=session.id,
    )

    session.raw_messages = result.raw_messages
    await db.flush()

    db.add(
        DataAcquisitionMessage(
            organization_id=organization_id,
            session_id=session.id,
            role="user",
            display_text=user_message,
        )
    )
    db.add(
        DataAcquisitionMessage(
            organization_id=organization_id,
            session_id=session.id,
            role="assistant",
            display_text=result.reply_text,
            staged_dataset_ids=staged_dataset_ids,
        )
    )
    await db.commit()

    return result.reply_text, staged_dataset_ids
