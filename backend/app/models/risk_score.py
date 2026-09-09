import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RiskScore(Base):
    """Combines a two-stage ("hurdle") model pair into one derived score:
    risk = P(positive_label | probability_model) * predicted_value(magnitude_model).
    Computed on demand at read time from each model's current
    active_candidate -- this row only stores which two models to combine
    and which classification label counts as "positive"."""

    __tablename__ = "risk_scores"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    probability_model_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    magnitude_model_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    positive_label: Mapped[str] = mapped_column(String, nullable=False, default="True")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
