from datetime import date, datetime

from pydantic import BaseModel


class RiskScoreCreate(BaseModel):
    name: str
    probability_model_id: str
    magnitude_model_id: str
    positive_label: str = "True"


class RiskScoreOut(BaseModel):
    id: str
    name: str
    probability_model_id: str
    magnitude_model_id: str
    positive_label: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskScoreRowOut(BaseModel):
    entity_id: str
    score_date: date
    probability: float
    predicted_magnitude: float
    risk_score: float


class RiskScoreResultOut(BaseModel):
    id: str
    name: str
    score_date: date | None = None
    rows: list[RiskScoreRowOut] = []
    total_row_count: int
