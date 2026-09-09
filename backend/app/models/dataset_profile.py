import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DatasetProfile(Base):
    __tablename__ = "dataset_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "content_hash", name="uq_dataset_profiles_org_hash"),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list] = mapped_column(JSON, nullable=False)
    ai_description: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_description_model: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_description_generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    profiled_at: Mapped[datetime] = mapped_column(server_default=func.now())
