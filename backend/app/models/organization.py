import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Organization(Base):
    __tablename__ = "organizations"

    # as_uuid=False: IDs are handled as plain strings at every API/dependency
    # boundary in this codebase (path params, JWT claims, Pydantic schemas),
    # so the ORM layer matches that rather than forcing uuid.UUID round-trips.
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    monthly_llm_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("20.00")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
