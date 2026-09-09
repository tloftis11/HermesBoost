"""Celery task: score a model's active candidate against fresh data.

Mirrors train_model.py's shape exactly -- a thin task wrapper bridging into
async code, one try/except around the whole body, a single commit on
success and on failure. Unlike train_model.py, a failed score run does NOT
set model.status = "error" -- the model itself is still ready and usable,
only this one score attempt failed.
"""

import asyncio
from datetime import datetime, timezone

import pandas as pd
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.db import async_session_maker, engine
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.models.scheduled_score import ScheduledScore
from app.services.ml.persistence import load_model_artifact
from app.services.ml.scoring_data import ScoringDataError, build_scoring_dataframe
from app.services.storage import get_storage_backend

logger = get_task_logger(__name__)


@celery_app.task(name="score_model", acks_late=True, soft_time_limit=600, time_limit=660)
def score_model(model_run_id: str) -> None:
    asyncio.run(_score_model_async(model_run_id))


async def _score_model_async(model_run_id: str) -> None:
    try:
        await _run(model_run_id)
    finally:
        # The engine's connection pool is a module-level singleton, but
        # each Celery task invocation gets its own fresh event loop via
        # asyncio.run() -- a pooled connection checked out in a *previous*
        # call's loop is invalid in this one (asyncpg raises "Future
        # attached to a different loop" if it's reused). Disposing here
        # ensures the next task invocation starts with an empty pool and
        # opens brand-new connections in its own loop, rather than handing
        # a stale one across the boundary.
        await engine.dispose()


async def _run(model_run_id: str) -> None:
    async with async_session_maker() as db:
        run = await db.get(ModelRun, model_run_id)
        if run is None:
            logger.warning("score_model: model_run %s not found", model_run_id)
            return

        model = await db.get(Model, run.model_id)
        spec = await db.get(ModelingSpec, model.modeling_spec_id)

        try:
            if model.status != "ready" or model.active_candidate_id is None:
                raise ScoringDataError("Model is not ready to score yet.")
            candidate = await db.get(ModelCandidate, model.active_candidate_id)

            data = await build_scoring_dataframe(db, spec)

            pipeline = load_model_artifact(
                get_storage_backend().download(candidate.storage_bucket, candidate.storage_path)
            )

            # Align to the candidate's own frozen feature shape, not
            # spec.candidate_features -- the spec can be edited after
            # training without a retrain.
            missing = [c for c in candidate.feature_columns if c not in data.dataframe.columns]
            if missing:
                raise ScoringDataError(f"Missing column(s) required by this model: {', '.join(missing)}")

            df = data.dataframe[candidate.feature_columns].copy()
            for col, dtype in candidate.feature_dtypes.items():
                if dtype == "numeric":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                else:
                    df[col] = df[col].astype(str)

            rows: list[ScheduledScore] = []
            if candidate.ml_task == "classification":
                proba = pipeline.predict_proba(df)
                pred_idx = proba.argmax(axis=1)
                for i, entity_id in enumerate(data.entity_ids):
                    rows.append(ScheduledScore(
                        organization_id=model.organization_id,
                        model_id=model.id,
                        model_run_id=run.id,
                        model_candidate_id=candidate.id,
                        entity_id=entity_id,
                        score_date=data.score_date,
                        predicted_label=candidate.label_classes[pred_idx[i]],
                        predicted_probability=float(proba[i, pred_idx[i]]),
                    ))
            else:
                predictions = pipeline.predict(df)
                for i, entity_id in enumerate(data.entity_ids):
                    rows.append(ScheduledScore(
                        organization_id=model.organization_id,
                        model_id=model.id,
                        model_run_id=run.id,
                        model_candidate_id=candidate.id,
                        entity_id=entity_id,
                        score_date=data.score_date,
                        predicted_value=float(predictions[i]),
                    ))

            db.add_all(rows)
            run.row_count_used = data.row_count
            run.warnings = data.warnings
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 -- mirrors train_model.py exactly
            logger.exception("score_model failed for run %s", model_run_id)
            run.status = "error"
            run.error_message = str(exc)[:500]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
