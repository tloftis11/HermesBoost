from datetime import datetime

from pydantic import BaseModel

from app.services.llm.modeling_spec_schema import Cadence, TaskType


class ModelingSpecOut(BaseModel):
    id: str
    dataset_id: str
    status: str
    task_type: TaskType | None = None
    task_description: str | None = None
    target: str | None = None
    candidate_features: list[str]
    evaluation_metric: str | None = None
    retrain_cadence: Cadence
    score_cadence: Cadence
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelingSpecUpdate(BaseModel):
    candidate_features: list[str] | None = None
    retrain_cadence: Cadence | None = None
    score_cadence: Cadence | None = None


class ChatMessageOut(BaseModel):
    role: str
    content: str  # always the human-readable text -- raw JSON storage detail never leaks here
    created_at: datetime


class ModelingSpecDetail(BaseModel):
    spec: ModelingSpecOut
    messages: list[ChatMessageOut]


class SendMessageRequest(BaseModel):
    message: str


class SendMessageResponse(BaseModel):
    reply_message: str
    spec: ModelingSpecOut
