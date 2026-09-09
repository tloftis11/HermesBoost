import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_STATUSES = ("training", "ready", "error")


class Model(Base):
    """The stable "slot" for a modeling spec's model -- one row per spec,
    created on first "Build models" click, reused across retrains. The
    frontend route /models/:id hangs off this id. active_candidate_id points
    at whichever ModelCandidate row is "the" model right now (starts as the
    recommended candidate from the latest run; a future "promote a
    baseline" feature is just flipping this pointer, no retrain needed)."""

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    modeling_spec_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("modeling_specs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="training")
    # User-settable, for addressing this model by name instead of only its
    # UUID (external API consumers). Nullable -- unset until named.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    active_candidate_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("model_candidates.id", use_alter=True, name="fk_models_active_candidate"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
