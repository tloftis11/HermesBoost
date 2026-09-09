import asyncio
import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from app.dependencies import CurrentOrgId, DbSession, OrgIdAnyAuth
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
from app.services.dataset_profiles import get_latest_profile
from app.services.ml.imbalance import is_imbalanced, minority_rate
from app.services.ml.task_mapping import UnsupportedTaskTypeError, to_ml_task
from app.services.profiling import TOP_VALUES_LIMIT
from app.tasks.score_model import score_model
from app.tasks.train_model import train_model

MAX_SCORE_ROWS = 500
MAX_CSV_ROWS = 50_000

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
        ml_task = None
        metric_label = None
        metric_value = None
        if model.active_candidate_id:
            candidate = await db.get(ModelCandidate, model.active_candidate_id)
            if candidate:
                algorithm = candidate.algorithm
                ml_task = candidate.ml_task
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
                ml_task=ml_task,
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

    if spec.task_type == "classification" and not spec.acknowledged_imbalance:
        await _raise_if_imbalanced_and_unacknowledged(db, spec)

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


@router.get("/models/{model_id}/scores", response_model=None)
async def get_scores(
    model_id: str,
    organization_id: OrgIdAnyAuth,
    db: DbSession,
    format: str = Query("json", pattern="^(json|csv)$"),
    score_date: date | None = None,
    score_date_from: date | None = None,
    score_date_to: date | None = None,
    entity_id: str | None = None,
    limit: int = Query(MAX_SCORE_ROWS, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> ScoreRunOut | Response:
    """Serves both the browser frontend (no query params -> today's latest
    score run, unchanged; CurrentOrgId-equivalent via the dev-mode/session
    fallback baked into OrgIdAnyAuth) and external API-key callers (date/
    entity filters, pagination, and ?format=csv) -- one query engine so
    export and the JSON API never drift apart."""
    model = await _get_org_model(db, model_id, organization_id)
    has_filters = any([score_date, score_date_from, score_date_to, entity_id])

    conditions = [ScheduledScore.model_id == model.id]
    run: ModelRun | None = None

    if has_filters:
        if entity_id:
            conditions.append(ScheduledScore.entity_id == entity_id)
        if score_date:
            conditions.append(ScheduledScore.score_date == score_date)
        else:
            if score_date_from:
                conditions.append(ScheduledScore.score_date >= score_date_from)
            if score_date_to:
                conditions.append(ScheduledScore.score_date <= score_date_to)
        order = [ScheduledScore.score_date.desc(), ScheduledScore.entity_id]
    else:
        # Default, no filters at all: the model's latest score run --
        # exactly today's existing behavior, byte-for-byte, so the
        # frontend's no-args call is unaffected.
        run = await _get_latest_run(db, model.id, run_type="score")
        if run is None:
            empty = ScoreRunOut(
                id=model.id, modeling_spec_id=model.modeling_spec_id, status=model.status,
                run=None, rows=[], total_row_count=None,
            )
            return _rows_to_csv_response([]) if format == "csv" else empty
        conditions.append(ScheduledScore.model_run_id == run.id)
        order = [ScheduledScore.entity_id]

    total_row_count = (
        await db.execute(select(func.count()).select_from(ScheduledScore).where(*conditions))
    ).scalar_one()

    if format == "csv":
        # Exports are "everything matching my filter," not a page --
        # limit/offset are ignored, capped at MAX_CSV_ROWS as a safety
        # ceiling instead.
        result = await db.execute(select(ScheduledScore).where(*conditions).order_by(*order).limit(MAX_CSV_ROWS))
        return _rows_to_csv_response(list(result.scalars().all()))

    result = await db.execute(select(ScheduledScore).where(*conditions).order_by(*order).limit(limit).offset(offset))
    rows = list(result.scalars().all())

    return ScoreRunOut(
        id=model.id,
        modeling_spec_id=model.modeling_spec_id,
        status=model.status,
        run=ModelRunOut.model_validate(run) if run else None,
        rows=[ScoredRowOut.model_validate(r) for r in rows],
        total_row_count=total_row_count,
    )


def _rows_to_csv_response(rows: list[ScheduledScore]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["entity_id", "score_date", "predicted_value", "predicted_label", "predicted_probability"])
    for r in rows:
        writer.writerow(
            [r.entity_id, r.score_date.isoformat(), r.predicted_value, r.predicted_label, r.predicted_probability]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=scores.csv"},
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


async def _raise_if_imbalanced_and_unacknowledged(db: DbSession, spec: ModelingSpec) -> None:
    """Fast, best-effort pre-flight check from the dataset's already-
    computed profile -- a courtesy warning before spending training
    compute. Deliberately skips (proceeds straight to training) when the
    target has more distinct classes than the profile's capped top_values
    list can reliably represent; train.py's own check on the real
    y_train, computed at fit time, is what actually decides whether class
    weighting gets applied, and is never skipped."""
    dataset = await db.get(Dataset, spec.dataset_id)
    if dataset is None:
        return
    profile = await get_latest_profile(db, dataset)
    if profile is None:
        return

    target_col = next((c for c in profile.columns if c["name"] == spec.target), None)
    if target_col is None or not target_col.get("top_values"):
        return
    if target_col.get("distinct_count", 0) > TOP_VALUES_LIMIT:
        return

    counts = {tv["value"]: tv["count"] for tv in target_col["top_values"]}
    rate = minority_rate(counts)
    if not is_imbalanced(rate):
        return

    raise HTTPException(
        status_code=400,
        detail={
            "code": "imbalance_ack_required",
            "minority_rate": rate,
            "message": (
                f"This target's minority class is only {rate:.1%} of rows. Building will apply "
                "class weighting during fitting and report an additional operating point (the "
                "threshold that maximizes F1) alongside the standard metrics. PATCH this spec "
                "with acknowledge_imbalance=true to proceed."
            ),
        },
    )


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
