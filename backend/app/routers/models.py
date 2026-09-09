import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentOrgId, DbSession
from app.models.dataset import Dataset
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.models.scheduled_score import ScheduledScore
from app.routers.modeling_specs import _get_org_spec
from app.schemas.model import (
    BuildResponse,
    LeaderboardOut,
    ModelCandidateOut,
    ModelGuidedOut,
    ModelListItemOut,
    ModelRunOut,
    PromoteCandidateRequest,
    ScoredRowOut,
    ScoreResponse,
    ScoreRunOut,
)
from app.services.ml.task_mapping import UnsupportedTaskTypeError, to_ml_task
from app.tasks.score_model import score_model
from app.tasks.train_model import train_model

MAX_SCORE_ROWS = 500

router = APIRouter(tags=["models"])

_PRIMARY_METRIC_BY_TASK = {"classification": ("auc", "AUC"), "regression": ("r2", "R²")}


@router.get("/models", response_model=list[ModelListItemOut])
async def list_models(organization_id: CurrentOrgId, db: DbSession) -> list[ModelListItemOut]:
    result = await db.execute(
        select(Model).where(Model.organization_id == organization_id).order_by(Model.updated_at.desc())
    )
    models = list(result.scalars().all())

    items: list[ModelListItemOut] = []
    for model in models:
        spec = await db.get(ModelingSpec, model.modeling_spec_id)
        dataset = await db.get(Dataset, spec.dataset_id) if spec else None

        algorithm = None
        metric_label = None
        metric_value = None
        if model.active_candidate_id:
            candidate = await db.get(ModelCandidate, model.active_candidate_id)
            if candidate:
                algorithm = candidate.algorithm
                metric_key_label = _PRIMARY_METRIC_BY_TASK.get(candidate.ml_task)
                if metric_key_label:
                    metric_key, metric_label = metric_key_label
                    metric_value = candidate.metrics.get(metric_key)

        items.append(
            ModelListItemOut(
                id=model.id,
                modeling_spec_id=model.modeling_spec_id,
                dataset_name=dataset.name if dataset else "(deleted dataset)",
                task_description=spec.task_description if spec else None,
                status=model.status,
                algorithm=algorithm,
                primary_metric_label=metric_label,
                primary_metric_value=metric_value,
                updated_at=model.updated_at,
            )
        )
    return items


@router.post("/modeling-specs/{spec_id}/build", response_model=BuildResponse, status_code=202)
async def build_model(spec_id: str, organization_id: CurrentOrgId, db: DbSession) -> BuildResponse:
    spec = await _get_org_spec(db, spec_id, organization_id)

    try:
        to_ml_task(spec.task_type)
    except UnsupportedTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await db.execute(
        select(Model).where(Model.modeling_spec_id == spec_id, Model.organization_id == organization_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        model = Model(organization_id=organization_id, modeling_spec_id=spec_id, status="training")
        db.add(model)
    else:
        model.status = "training"
        model.error_message = None
    await db.flush()

    run = ModelRun(organization_id=organization_id, model_id=model.id, run_type="train", status="running")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # .to_thread avoids the nested-event-loop crash under
    # CELERY_TASK_ALWAYS_EAGER, same reasoning as datasets.py's upload endpoint.
    await asyncio.to_thread(train_model.delay, run.id)

    return BuildResponse(model_id=model.id, model_run_id=run.id)


@router.get("/models/{model_id}", response_model=ModelGuidedOut)
async def get_model(model_id: str, organization_id: CurrentOrgId, db: DbSession) -> ModelGuidedOut:
    model = await _get_org_model(db, model_id, organization_id)
    latest_run = await _get_latest_run(db, model.id)

    active_candidate = None
    if model.active_candidate_id:
        active_candidate = await db.get(ModelCandidate, model.active_candidate_id)

    return ModelGuidedOut(
        id=model.id,
        modeling_spec_id=model.modeling_spec_id,
        status=model.status,
        error_message=model.error_message,
        active_candidate=ModelCandidateOut.model_validate(active_candidate) if active_candidate else None,
        latest_run=ModelRunOut.model_validate(latest_run) if latest_run else None,
    )


@router.get("/models/{model_id}/leaderboard", response_model=LeaderboardOut)
async def get_leaderboard(model_id: str, organization_id: CurrentOrgId, db: DbSession) -> LeaderboardOut:
    model = await _get_org_model(db, model_id, organization_id)
    latest_run = await _get_latest_run(db, model.id)

    candidates: list[ModelCandidate] = []
    if latest_run is not None:
        result = await db.execute(
            select(ModelCandidate).where(ModelCandidate.model_run_id == latest_run.id)
        )
        candidates = list(result.scalars().all())
        # Sorted in Python, not SQL: all 4 rows are inserted in one
        # transaction, and Postgres's now() is constant for the whole
        # transaction, so created_at can't be trusted to break ties.
        candidates.sort(key=lambda c: 0 if c.role == "recommended" else 1)

    return LeaderboardOut(
        id=model.id,
        modeling_spec_id=model.modeling_spec_id,
        status=model.status,
        candidates=[ModelCandidateOut.model_validate(c) for c in candidates],
        run=ModelRunOut.model_validate(latest_run) if latest_run else None,
    )


@router.post("/models/{model_id}/score", response_model=ScoreResponse, status_code=202)
async def score_model_endpoint(model_id: str, organization_id: CurrentOrgId, db: DbSession) -> ScoreResponse:
    model = await _get_org_model(db, model_id, organization_id)
    if model.status != "ready":
        raise HTTPException(status_code=400, detail="Model must be ready before it can be scored.")

    run = ModelRun(organization_id=organization_id, model_id=model.id, run_type="score", status="running")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await asyncio.to_thread(score_model.delay, run.id)

    return ScoreResponse(model_id=model.id, model_run_id=run.id)


@router.get("/models/{model_id}/scores", response_model=ScoreRunOut)
async def get_scores(model_id: str, organization_id: CurrentOrgId, db: DbSession) -> ScoreRunOut:
    model = await _get_org_model(db, model_id, organization_id)
    latest_run = await _get_latest_run(db, model.id, run_type="score")

    rows: list[ScheduledScore] = []
    if latest_run is not None:
        result = await db.execute(
            select(ScheduledScore)
            .where(ScheduledScore.model_run_id == latest_run.id)
            .order_by(ScheduledScore.entity_id)
            .limit(MAX_SCORE_ROWS)
        )
        rows = list(result.scalars().all())

    return ScoreRunOut(
        id=model.id,
        modeling_spec_id=model.modeling_spec_id,
        status=model.status,
        run=ModelRunOut.model_validate(latest_run) if latest_run else None,
        rows=[ScoredRowOut.model_validate(r) for r in rows],
        total_row_count=latest_run.row_count_used if latest_run else None,
    )


@router.post("/models/{model_id}/promote", response_model=ModelGuidedOut)
async def promote_candidate(
    model_id: str, body: PromoteCandidateRequest, organization_id: CurrentOrgId, db: DbSession
) -> ModelGuidedOut:
    model = await _get_org_model(db, model_id, organization_id)

    candidate = await db.get(ModelCandidate, body.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    run = await db.get(ModelRun, candidate.model_run_id)
    if run is None or str(run.model_id) != str(model.id):
        raise HTTPException(status_code=404, detail="Candidate not found")

    model.active_candidate_id = candidate.id
    await db.commit()

    return await get_model(model.id, organization_id, db)


@router.get("/modeling-specs/{spec_id}/models", response_model=ModelGuidedOut)
async def get_model_for_spec(spec_id: str, organization_id: CurrentOrgId, db: DbSession) -> ModelGuidedOut:
    await _get_org_spec(db, spec_id, organization_id)  # 404s if not this org's
    result = await db.execute(
        select(Model).where(Model.modeling_spec_id == spec_id, Model.organization_id == organization_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="No model has been built for this spec yet")
    return await get_model(model.id, organization_id, db)


async def _get_org_model(db: DbSession, model_id: str, organization_id: str) -> Model:
    try:
        uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found") from None

    model = await db.get(Model, model_id)
    if model is None or str(model.organization_id) != str(organization_id):
        raise HTTPException(status_code=404, detail="Model not found")
    return model


async def _get_latest_run(db: DbSession, model_id: str, run_type: str = "train") -> ModelRun | None:
    result = await db.execute(
        select(ModelRun)
        .where(ModelRun.model_id == model_id, ModelRun.run_type == run_type)
        .order_by(ModelRun.started_at.desc())
    )
    return result.scalars().first()
