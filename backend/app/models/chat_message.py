import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_ROLES = ("user", "assistant")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    modeling_spec_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("modeling_specs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    # For role='assistant', this is the raw JSON the model returned (the
    # serialized ChatTurnResponse) -- not just the display text. Replaying
    # that back as history next turn is how the model sees its own prior
    # structured spec state. role='user' rows are plain text.
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
