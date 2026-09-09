from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LlmTaskModelConfig(Base):
    __tablename__ = "llm_task_model_config"

    task_type: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, nullable=False, default="claude-opus-5")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
