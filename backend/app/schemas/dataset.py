from datetime import datetime

from pydantic import BaseModel


class DatasetCreateResponse(BaseModel):
    id: str
    status: str


class DatasetOut(BaseModel):
    id: str
    name: str
    status: str
    row_count: int | None = None
    column_count: int | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
