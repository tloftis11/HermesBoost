from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class BuildResponse(BaseModel):
    model_id: str
    model_run_id: str


class ModelCandidateOut(BaseModel):
    id: str
    role: str
    algorithm: str
    ml_task: str
    metrics: dict
    feature_importance: list[dict] | None = None
    hyperparams: dict | None = None
    train_time_seconds: Decimal | None = None

    model_config = {"from_attributes": True}


class ModelRunOut(BaseModel):
    id: str
    status: str
    ml_task: str | None = None
    row_count_used: int | None = None
    warnings: list[str] | None = None
    interpretation_summary: str | None = None
    interpretation_key_drivers: list[dict] | None = None
    interpretation_model: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ModelGuidedOut(BaseModel):
    """Guided-view shape: the model's status plus the active candidate and
    the latest run's interpretation -- everything the guided screen needs."""

    id: str
    modeling_spec_id: str
    name: str | None = None
    status: str
    error_message: str | None = None
    active_candidate: ModelCandidateOut | None = None
    latest_run: ModelRunOut | None = None


class LeaderboardOut(BaseModel):
    """Advanced-view shape: every candidate from the latest run, plus run
    metadata."""

    id: str
    modeling_spec_id: str
    status: str
    candidates: list[ModelCandidateOut]
    run: ModelRunOut | None = None


class ModelListItemOut(BaseModel):
    """One row of the org-wide models list -- everything the list page
    needs without a follow-up request per row."""

    id: str
    modeling_spec_id: str
    name: str | None = None
    dataset_name: str
    task_description: str | None = None
    status: str
    algorithm: str | None = None
    ml_task: str | None = None
    primary_metric_label: str | None = None
    primary_metric_value: float | None = None
    updated_at: datetime


class ModelUpdate(BaseModel):
    name: str


class ResponseFieldDoc(BaseModel):
    field: str
    meaning: str


class UsageDocOut(BaseModel):
    what_it_predicts: str
    response_fields: list[ResponseFieldDoc]
    curl_example: str


class ScoreResponse(BaseModel):
    model_id: str
    model_run_id: str


class ScoredRowOut(BaseModel):
    id: str
    entity_id: str
    score_date: date
    predicted_value: float | None = None
    predicted_label: str | None = None
    predicted_probability: float | None = None

    model_config = {"from_attributes": True}


class ScoreRunOut(BaseModel):
    """Advanced-view shape for the Scores tab: run metadata plus the rows
    it produced, capped at a sane count for a first version."""

    id: str
    modeling_spec_id: str
    status: str
    run: ModelRunOut | None = None
    rows: list[ScoredRowOut] = []
    total_row_count: int | None = None


class PromoteCandidateRequest(BaseModel):
    candidate_id: str
