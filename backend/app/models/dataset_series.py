import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DatasetSeries(Base):
    """A named recurring feed (design doc §4.6). Schema only this milestone
    -- datasets.series_id/as_of_date can tag into one, but nothing creates
    rows here yet; no automated ingestion exists."""

    __tablename__ = "dataset_series"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_dataset_series_org_name"),)

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
