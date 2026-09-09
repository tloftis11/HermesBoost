import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_JOIN_TYPES = ("left", "inner")


class ModelingSpecJoinDataset(Base):
    __tablename__ = "modeling_spec_join_datasets"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    modeling_spec_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("modeling_specs.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("datasets.id"), nullable=False
    )
    join_key_column: Mapped[str] = mapped_column(String, nullable=False)
    join_type: Mapped[str] = mapped_column(String, nullable=False, default="left")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
