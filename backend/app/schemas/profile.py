from datetime import datetime

from pydantic import BaseModel


class TopValue(BaseModel):
    value: str
    count: int


class ColumnProfileOut(BaseModel):
    name: str
    dtype: str  # "numeric" | "categorical" | "id"
    null_rate: float
    distinct_count: int
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    top_values: list[TopValue] | None = None
    histogram: list[int] | None = None  # 8-bucket counts, numeric columns only


class DatasetProfileOut(BaseModel):
    status: str  # "profiling" | "profiled" | "error"
    row_count: int | None = None
    column_count: int | None = None
    columns: list[ColumnProfileOut] | None = None
    ai_description: str | None = None
    ai_description_model: str | None = None
    profiled_at: datetime | None = None
    error_message: str | None = None
