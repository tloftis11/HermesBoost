import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentOrgId, DbSession
from app.models.data_acquisition import DataAcquisitionMessage, DataAcquisitionSession
from app.schemas.data_acquisition import (
    DataAcquisitionMessageIn,
    DataAcquisitionMessageOut,
    DataAcquisitionSessionCreate,
    DataAcquisitionSessionDetail,
    DataAcquisitionSessionOut,
    DataAcquisitionTurnResponse,
)
from app.services.llm.data_acquisition import run_data_acquisition_turn

router = APIRouter(prefix="/data-acquisition-sessions", tags=["data-acquisition"])


@router.post("", response_model=DataAcquisitionTurnResponse, status_code=201)
async def create_session(
    body: DataAcquisitionSessionCreate, organization_id: CurrentOrgId, db: DbSession
) -> DataAcquisitionTurnResponse:
    session = DataAcquisitionSession(
        organization_id=organization_id, problem_description=body.problem_description
    )
    db.add(session)
    await db.flush()

    reply_message, staged_dataset_ids = await run_data_acquisition_turn(
        db, organization_id, session, body.problem_description
    )
    await db.refresh(session)

    return DataAcquisitionTurnResponse(
        session=DataAcquisitionSessionOut.model_validate(session),
        reply_message=reply_message,
        staged_dataset_ids=staged_dataset_ids,
    )


@router.post("/{session_id}/messages", response_model=DataAcquisitionTurnResponse)
async def send_message(
    session_id: str, body: DataAcquisitionMessageIn, organization_id: CurrentOrgId, db: DbSession
) -> DataAcquisitionTurnResponse:
    session = await _get_org_session(db, session_id, organization_id)

    reply_message, staged_dataset_ids = await run_data_acquisition_turn(
        db, organization_id, session, body.message
    )
    await db.refresh(session)

    return DataAcquisitionTurnResponse(
        session=DataAcquisitionSessionOut.model_validate(session),
        reply_message=reply_message,
        staged_dataset_ids=staged_dataset_ids,
    )


@router.get("/{session_id}", response_model=DataAcquisitionSessionDetail)
async def get_session(
    session_id: str, organization_id: CurrentOrgId, db: DbSession
) -> DataAcquisitionSessionDetail:
    session = await _get_org_session(db, session_id, organization_id)
    result = await db.execute(
        select(DataAcquisitionMessage)
        .where(DataAcquisitionMessage.session_id == session_id)
        .order_by(DataAcquisitionMessage.created_at.asc())
    )
    messages = list(result.scalars().all())

    return DataAcquisitionSessionDetail(
        session=DataAcquisitionSessionOut.model_validate(session),
        messages=[DataAcquisitionMessageOut.model_validate(m) for m in messages],
    )


async def _get_org_session(db: DbSession, session_id: str, organization_id: str) -> DataAcquisitionSession:
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    session = await db.get(DataAcquisitionSession, session_id)
    if session is None or str(session.organization_id) != str(organization_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return session
