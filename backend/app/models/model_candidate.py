import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_ROLES = ("recommended", "baseline")


class ModelCandidate(Base):
    """One fitted algorithm produced by a ModelRun -- 4 rows per successful
    run (1 recommended, from FLAML's search, + 3 fixed-hyperparameter
    baselines). Each is fully self-contained for future inference: feature
    columns/dtypes, target column, label classes, metrics, importance,
    hyperparams, and its own storage path."""

    __tablename__ = "model_candidates"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    model_run_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    algorithm: Mapped[str] = mapped_column(String, nullable=False)
    ml_task: Mapped[str] = mapped_column(String, nullable=False)
    feature_columns: Mapped[list] = mapped_column(JSON, nullable=False)
    feature_dtypes: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_column: Mapped[str] = mapped_column(String, nullable=False)
    label_classes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    feature_importance: Mapped[list | None] = mapped_column(JSON, nullable=True)
    hyperparams: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    train_time_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
