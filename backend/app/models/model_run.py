import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_RUN_TYPES = ("train", "score")
VALID_STATUSES = ("running", "completed", "error")


class ModelRun(Base):
    """One training attempt for a Model. run_type is 'train' today;
    'score' is reserved for the scheduling milestone, which will reuse this
    same table rather than inventing a parallel one."""

    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(String, nullable=False, default="train")
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    ml_task: Mapped[str | None] = mapped_column(String, nullable=True)
    row_count_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    interpretation_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    interpretation_key_drivers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    interpretation_model: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
