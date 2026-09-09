from datetime import datetime
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
    dataset_name: str
    task_description: str | None = None
    status: str
    algorithm: str | None = None
    primary_metric_label: str | None = None
    primary_metric_value: float | None = None
    updated_at: datetime
