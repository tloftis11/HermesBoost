import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiKey(Base):
    """A real, revocable, per-organization API key. Only key_hash (sha256
    of the raw key) is ever persisted -- the raw key is shown to the user
    exactly once, at creation, and never stored or displayed again."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
