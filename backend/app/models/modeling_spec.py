import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_STATUSES = ("draft", "confirmed")
VALID_CADENCES = ("daily", "weekly", "monthly")


class ModelingSpec(Base):
    __tablename__ = "modeling_specs"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    task_type: Mapped[str | None] = mapped_column(String, nullable=True)
    task_description: Mapped[str | None] = mapped_column(String, nullable=True)
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_features: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation_metric: Mapped[str | None] = mapped_column(String, nullable=True)
    retrain_cadence: Mapped[str] = mapped_column(String, nullable=False, default="weekly")
    score_cadence: Mapped[str] = mapped_column(String, nullable=False, default="daily")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
