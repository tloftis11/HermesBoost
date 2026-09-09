"""The contract between the intent-chat LLM call and everything downstream.

Passed directly as `output_format` to client.messages.parse() -- the model's
entire response is constrained to this shape, so `reply_message` (the chat
bubble text) and `modeling_spec` (the structured spec) always arrive together
in one call, no tool-use loop needed.
"""

from typing import Literal

from pydantic import BaseModel

TaskType = Literal[
    "risk_scoring",
    "classification",
    "regression",
    "time_series_forecast",
    "clustering",
    "anomaly_detection",
]
Cadence = Literal["daily", "weekly", "monthly"]


class ModelingSpecFields(BaseModel):
    task_type: TaskType
    task_description: str
    target: str
    candidate_features: list[str]
    evaluation_metric: str
    entity_id_column: str | None = None
    retrain_cadence: Cadence
    score_cadence: Cadence


class ChatTurnResponse(BaseModel):
    reply_message: str
    # None only on the very first turn or two, before enough is known to
    # propose anything -- once a spec exists, every later turn should
    # re-emit the FULL current state (carrying forward unchanged fields),
    # not a partial diff.
    modeling_spec: ModelingSpecFields | None = None
