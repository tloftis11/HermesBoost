"""Combines a two-stage ("hurdle") model pair into one exposed risk score:
risk = P(positive_label | probability_model) * predicted_value(magnitude_model).

Computed on demand at read time, directly from each model's current
active_candidate -- see the plan's "Key design decision" for why this
reuses build_scoring_dataframe once (against the probability model's
natural scoring universe) rather than adding a dataset override to the
shared scoring pipeline. No new Celery task, no new run/score tables.
"""

import csv
import io
import uuid

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.config import settings
from app.dependencies import CurrentOrgId, DbSession, OrgIdAnyAuth
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.modeling_spec import ModelingSpec
from app.models.risk_score import RiskScore
from app.routers.models import _get_org_model
from app.schemas.model import ResponseFieldDoc, UsageDocOut
from app.schemas.risk_score import (
    RiskScoreCreate,
    RiskScoreOut,
    RiskScoreResultOut,
    RiskScoreRowOut,
)
from app.services.ml.persistence import load_model_artifact
from app.services.ml.scoring_data import ScoringDataError, build_scoring_dataframe
from app.services.storage import get_storage_backend

MAX_ROWS = 5000

router = APIRouter(prefix="/risk-scores", tags=["risk-scores"])


@router.post("", response_model=RiskScoreOut, status_code=201)
async def create_risk_score(
    body: RiskScoreCreate, organization_id: CurrentOrgId, db: DbSession
) -> RiskScore:
    if body.probability_model_id == body.magnitude_model_id:
        raise HTTPException(status_code=400, detail="Choose two different models to combine.")

    existing = await db.execute(
        select(RiskScore).where(RiskScore.organization_id == organization_id, RiskScore.name == body.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"A risk score named '{body.name}' already exists.")

    prob_model = await _get_org_model(db, body.probability_model_id, organization_id)
    mag_model = await _get_org_model(db, body.magnitude_model_id, organization_id)

    prob_candidate, mag_candidate = await _require_ready_candidates(db, prob_model, mag_model)

    if prob_candidate.ml_task != "classification":
        raise HTTPException(
            status_code=400,
            detail="The probability model must be a classification model.",
        )
    if mag_candidate.ml_task != "regression":
        raise HTTPException(
            status_code=400,
            detail="The magnitude model must be a regression model.",
        )

    label_classes = prob_candidate.label_classes or []
    if body.positive_label not in label_classes:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.positive_label}' is not one of this model's classes: {label_classes}.",
        )

    missing = [c for c in mag_candidate.feature_columns if c not in prob_candidate.feature_columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "The magnitude model uses feature(s) the probability model doesn't: "
                f"{missing}. Both models must share a compatible feature set so one "
                "scoring pass can serve both."
            ),
        )

    risk_score = RiskScore(
        organization_id=organization_id,
        name=body.name,
        probability_model_id=prob_model.id,
        magnitude_model_id=mag_model.id,
        positive_label=body.positive_label,
    )
    db.add(risk_score)
    await db.commit()
    await db.refresh(risk_score)
    return risk_score


@router.get("", response_model=list[RiskScoreOut])
async def list_risk_scores(organization_id: CurrentOrgId, db: DbSession) -> list[RiskScore]:
    result = await db.execute(
        select(RiskScore)
        .where(RiskScore.organization_id == organization_id)
        .order_by(RiskScore.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{risk_score_id}", response_model=RiskScoreOut)
async def get_risk_score(risk_score_id: str, organization_id: CurrentOrgId, db: DbSession) -> RiskScore:
    return await _get_org_risk_score(db, risk_score_id, organization_id)


@router.delete("/{risk_score_id}", status_code=204)
async def delete_risk_score(risk_score_id: str, organization_id: CurrentOrgId, db: DbSession) -> None:
    risk_score = await _get_org_risk_score(db, risk_score_id, organization_id)
    await db.delete(risk_score)
    await db.commit()


@router.get("/{risk_score_id}/scores", response_model=None)
async def get_risk_scores(
    risk_score_id: str,
    organization_id: OrgIdAnyAuth,
    db: DbSession,
    format: str = Query("json", pattern="^(json|csv)$"),
    entity_id: str | None = None,
) -> RiskScoreResultOut | Response:
    risk_score = await _get_org_risk_score(db, risk_score_id, organization_id)

    prob_model = await db.get(Model, risk_score.probability_model_id)
    mag_model = await db.get(Model, risk_score.magnitude_model_id)
    prob_candidate, mag_candidate = await _require_ready_candidates(db, prob_model, mag_model)

    spec = await db.get(ModelingSpec, prob_model.modeling_spec_id)
    try:
        data = await build_scoring_dataframe(db, spec)
    except ScoringDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = get_storage_backend()
    prob_pipeline = load_model_artifact(storage.download(prob_candidate.storage_bucket, prob_candidate.storage_path))
    mag_pipeline = load_model_artifact(storage.download(mag_candidate.storage_bucket, mag_candidate.storage_path))

    df_prob = _select_and_coerce(data.dataframe, prob_candidate)
    df_mag = _select_and_coerce(data.dataframe, mag_candidate)

    label_index = prob_candidate.label_classes.index(risk_score.positive_label)
    probability = prob_pipeline.predict_proba(df_prob)[:, label_index]
    predicted_magnitude = mag_pipeline.predict(df_mag)

    rows = [
        RiskScoreRowOut(
            entity_id=data.entity_ids[i],
            score_date=data.score_date,
            probability=float(probability[i]),
            predicted_magnitude=float(predicted_magnitude[i]),
            risk_score=float(probability[i] * predicted_magnitude[i]),
        )
        for i in range(len(data.entity_ids))
    ]
    if entity_id:
        rows = [r for r in rows if r.entity_id == entity_id]
    rows.sort(key=lambda r: r.risk_score, reverse=True)
    rows = rows[:MAX_ROWS]

    if format == "csv":
        return _rows_to_csv_response(rows)

    return RiskScoreResultOut(
        id=risk_score.id,
        name=risk_score.name,
        score_date=data.score_date,
        rows=rows,
        total_row_count=len(rows),
    )


@router.get("/{risk_score_id}/usage", response_model=UsageDocOut)
async def get_risk_score_usage(
    risk_score_id: str, organization_id: OrgIdAnyAuth, db: DbSession
) -> UsageDocOut:
    risk_score = await _get_org_risk_score(db, risk_score_id, organization_id)

    reference = risk_score.name or risk_score.id
    base_url = settings.PUBLIC_API_BASE_URL or "https://your-api-domain.example.com"
    curl_example = (
        f"curl -H \"X-API-Key: $HERMESBOOST_API_KEY\" "
        f"\"{base_url}/api/v1/risk-scores/{reference}/scores\""
    )
    if not settings.PUBLIC_API_BASE_URL:
        curl_example += "\n# Replace the host above with this org's real API base URL."
    curl_example += "\n# Create an API key from the Settings page."

    return UsageDocOut(
        what_it_predicts=(
            f"Combines two models into one ranked score: the probability of "
            f"'{risk_score.positive_label}' times the predicted magnitude if it "
            f"occurs -- higher risk_score means higher combined risk."
        ),
        response_fields=[
            ResponseFieldDoc(field="entity_id", meaning="Which row/entity this score is for."),
            ResponseFieldDoc(field="score_date", meaning="The date this score was computed for."),
            ResponseFieldDoc(
                field="probability", meaning=f"Predicted probability of '{risk_score.positive_label}', 0 to 1."
            ),
            ResponseFieldDoc(
                field="predicted_magnitude", meaning="Predicted magnitude from the second-stage model."
            ),
            ResponseFieldDoc(
                field="risk_score", meaning="probability * predicted_magnitude -- the combined, ranked score."
            ),
        ],
        curl_example=curl_example,
    )


def _select_and_coerce(df: pd.DataFrame, candidate: ModelCandidate) -> pd.DataFrame:
    missing = [c for c in candidate.feature_columns if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing column(s) required by this model: {', '.join(missing)}",
        )
    out = df[candidate.feature_columns].copy()
    for col, dtype in candidate.feature_dtypes.items():
        if dtype == "numeric":
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = out[col].astype(str)
    return out


def _rows_to_csv_response(rows: list[RiskScoreRowOut]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["entity_id", "score_date", "probability", "predicted_magnitude", "risk_score"])
    for r in rows:
        writer.writerow([r.entity_id, r.score_date.isoformat(), r.probability, r.predicted_magnitude, r.risk_score])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=risk_scores.csv"},
    )


async def _require_ready_candidates(
    db: DbSession, prob_model: Model, mag_model: Model
) -> tuple[ModelCandidate, ModelCandidate]:
    for model, role in ((prob_model, "probability"), (mag_model, "magnitude")):
        if model.status != "ready" or model.active_candidate_id is None:
            raise HTTPException(status_code=400, detail=f"The {role} model must be ready before it can be combined.")

    prob_candidate = await db.get(ModelCandidate, prob_model.active_candidate_id)
    mag_candidate = await db.get(ModelCandidate, mag_model.active_candidate_id)
    return prob_candidate, mag_candidate


async def _get_org_risk_score(db: DbSession, risk_score_id: str, organization_id: str) -> RiskScore:
    try:
        uuid.UUID(risk_score_id)
    except ValueError:
        # Not a UUID -- treat it as the risk score's (unique, required) name.
        result = await db.execute(
            select(RiskScore).where(RiskScore.organization_id == organization_id, RiskScore.name == risk_score_id)
        )
        risk_score = result.scalar_one_or_none()
        if risk_score is None:
            raise HTTPException(status_code=404, detail="Risk score not found")
        return risk_score

    risk_score = await db.get(RiskScore, risk_score_id)
    if risk_score is None or str(risk_score.organization_id) != str(organization_id):
        raise HTTPException(status_code=404, detail="Risk score not found")
    return risk_score
