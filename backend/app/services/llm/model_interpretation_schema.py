"""The contract between the model-interpretation LLM call and everything
downstream. Passed as `output_format` to client.messages.parse() -- same
structured-output pattern as modeling_spec_schema.py's ChatTurnResponse."""

from pydantic import BaseModel


class KeyDriver(BaseModel):
    feature: str
    plain_description: str
    relative_importance: float  # 0-1, normalized


class ModelInterpretationResult(BaseModel):
    summary_text: str
    key_drivers: list[KeyDriver]
