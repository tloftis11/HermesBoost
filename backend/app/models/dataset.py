import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VALID_STATUSES = ("uploaded", "profiling", "profiled", "error")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String, nullable=False, default="datasets")
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # Recurring-feed tagging (design doc §4.6) -- nullable, unused until a
    # later milestone builds series-aware ingestion/UI.
    series_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("dataset_series.id"), nullable=True
    )
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
