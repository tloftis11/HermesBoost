import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ScheduledScore(Base):
    """One scored entity from one score run -- strictly append-only, never
    updated or upserted. predicted_value is regression-only; predicted_label
    /predicted_probability are classification-only."""

    __tablename__ = "scheduled_scores"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    model_run_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    model_candidate_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("model_candidates.id"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_label: Mapped[str | None] = mapped_column(String, nullable=True)
    predicted_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
