import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentOrgId, DbSession
from app.models.chat_message import ChatMessage
from app.models.modeling_spec import ModelingSpec
from app.routers.datasets import _get_org_dataset
from app.schemas.modeling_spec import (
    ChatMessageOut,
    ModelingSpecDetail,
    ModelingSpecOut,
    ModelingSpecUpdate,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.dataset_profiles import get_latest_profile
from app.services.llm.modeling_spec_schema import ChatTurnResponse
from app.services.llm.prompts import build_intent_chat_system_prompt
from app.services.llm.provider import RefusalError, get_llm_provider

router = APIRouter(tags=["modeling-specs"])


@router.post(
    "/datasets/{dataset_id}/modeling-specs",
    response_model=ModelingSpecOut,
    status_code=201,
)
async def create_modeling_spec(
    dataset_id: str, organization_id: CurrentOrgId, db: DbSession
) -> ModelingSpecOut:
    dataset = await _get_org_dataset(db, dataset_id, organization_id)
    if dataset.status != "profiled":
        raise HTTPException(
            status_code=400,
            detail="Dataset must finish profiling before starting an analysis",
        )

    spec = ModelingSpec(organization_id=organization_id, dataset_id=dataset.id)
    db.add(spec)
    await db.commit()
    await db.refresh(spec)
    return spec


@router.get("/datasets/{dataset_id}/modeling-specs", response_model=list[ModelingSpecOut])
async def list_modeling_specs(
    dataset_id: str, organization_id: CurrentOrgId, db: DbSession
) -> list[ModelingSpec]:
    await _get_org_dataset(db, dataset_id, organization_id)  # 404s if not this org's
    result = await db.execute(
        select(ModelingSpec)
        .where(ModelingSpec.dataset_id == dataset_id, ModelingSpec.organization_id == organization_id)
        .order_by(ModelingSpec.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/modeling-specs/{spec_id}", response_model=ModelingSpecDetail)
async def get_modeling_spec(
    spec_id: str, organization_id: CurrentOrgId, db: DbSession
) -> ModelingSpecDetail:
    spec = await _get_org_spec(db, spec_id, organization_id)
    messages = await _load_messages(db, spec_id)
    return ModelingSpecDetail(spec=spec, messages=[_to_message_out(m) for m in messages])


@router.post("/modeling-specs/{spec_id}/messages", response_model=SendMessageResponse)
async def send_message(
    spec_id: str,
    body: SendMessageRequest,
    organization_id: CurrentOrgId,
    db: DbSession,
) -> SendMessageResponse:
    spec = await _get_org_spec(db, spec_id, organization_id)
    dataset = await _get_org_dataset(db, spec.dataset_id, organization_id)
    profile = await get_latest_profile(db, dataset)
    columns = profile.columns if profile else []

    history = await _load_messages(db, spec_id)
    api_messages = [{"role": m.role, "content": m.content} for m in history]
    api_messages.append({"role": "user", "content": body.message})

    system = build_intent_chat_system_prompt(dataset.name, columns)

    try:
        result = await get_llm_provider().complete_structured(
            db=db,
            task_type="intent_chat",
            organization_id=organization_id,
            messages=api_messages,
            output_format=ChatTurnResponse,
            system=system,
            trigger=f"modeling_spec:{spec_id}",
            related_table="modeling_specs",
            related_id=spec_id,
        )
    except RefusalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    parsed: ChatTurnResponse = result.parsed

    db.add(ChatMessage(organization_id=organization_id, modeling_spec_id=spec_id, role="user", content=body.message))
    db.add(
        ChatMessage(
            organization_id=organization_id,
            modeling_spec_id=spec_id,
            role="assistant",
            content=parsed.model_dump_json(),
        )
    )

    if parsed.modeling_spec is not None:
        fields = parsed.modeling_spec
        spec.task_type = fields.task_type
        spec.task_description = fields.task_description
        spec.target = fields.target
        spec.candidate_features = fields.candidate_features
        spec.evaluation_metric = fields.evaluation_metric
        spec.retrain_cadence = fields.retrain_cadence
        spec.score_cadence = fields.score_cadence

    await db.commit()
    await db.refresh(spec)

    return SendMessageResponse(reply_message=parsed.reply_message, spec=spec)


@router.patch("/modeling-specs/{spec_id}", response_model=ModelingSpecOut)
async def update_modeling_spec(
    spec_id: str,
    body: ModelingSpecUpdate,
    organization_id: CurrentOrgId,
    db: DbSession,
) -> ModelingSpec:
    spec = await _get_org_spec(db, spec_id, organization_id)

    if body.candidate_features is not None:
        spec.candidate_features = body.candidate_features
    if body.retrain_cadence is not None:
        spec.retrain_cadence = body.retrain_cadence
    if body.score_cadence is not None:
        spec.score_cadence = body.score_cadence

    await db.commit()
    await db.refresh(spec)
    return spec


async def _get_org_spec(db: DbSession, spec_id: str, organization_id: str) -> ModelingSpec:
    try:
        uuid.UUID(spec_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Modeling spec not found") from None

    spec = await db.get(ModelingSpec, spec_id)
    if spec is None or str(spec.organization_id) != str(organization_id):
        raise HTTPException(status_code=404, detail="Modeling spec not found")
    return spec


async def _load_messages(db: DbSession, spec_id: str) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.modeling_spec_id == spec_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


def _to_message_out(message: ChatMessage) -> ChatMessageOut:
    content = message.content
    if message.role == "assistant":
        try:
            content = ChatTurnResponse.model_validate_json(message.content).reply_message
        except Exception:
            pass  # fall back to raw content rather than 500 on a malformed row
    return ChatMessageOut(role=message.role, content=content, created_at=message.created_at)
