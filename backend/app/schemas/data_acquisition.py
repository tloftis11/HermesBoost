from datetime import datetime

from pydantic import BaseModel


class DataAcquisitionSessionCreate(BaseModel):
    problem_description: str


class DataAcquisitionMessageIn(BaseModel):
    message: str


class DataAcquisitionSessionOut(BaseModel):
    id: str
    problem_description: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DataAcquisitionMessageOut(BaseModel):
    role: str
    display_text: str
    staged_dataset_ids: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DataAcquisitionTurnResponse(BaseModel):
    session: DataAcquisitionSessionOut
    reply_message: str
    staged_dataset_ids: list[str]


class DataAcquisitionSessionDetail(BaseModel):
    session: DataAcquisitionSessionOut
    messages: list[DataAcquisitionMessageOut]
