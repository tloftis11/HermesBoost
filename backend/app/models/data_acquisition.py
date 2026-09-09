import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_STATUSES = ("active", "done")
VALID_ROLES = ("user", "assistant")


class DataAcquisitionSession(Base):
    """One research conversation with the data-acquisition assistant.
    raw_messages holds the full Anthropic-format history -- including
    tool_use/tool_result blocks -- since correctly resuming a tool-loop
    conversation requires replaying those, not just display text."""

    __tablename__ = "data_acquisition_sessions"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    problem_description: Mapped[str] = mapped_column(String, nullable=False)
    raw_messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataAcquisitionMessage(Base):
    """One turn's human-readable projection -- what the chat UI renders.
    display_text summarizes tool calls in plain English (e.g. "Searched
    for X", "Staged Y for your review") rather than showing raw blocks."""

    __tablename__ = "data_acquisition_messages"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("data_acquisition_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    display_text: Mapped[str] = mapped_column(String, nullable=False)
    staged_dataset_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
