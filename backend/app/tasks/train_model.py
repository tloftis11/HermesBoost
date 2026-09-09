"""Celery task: build and compare candidate models for a modeling spec.

Mirrors profile_dataset.py's shape exactly: a thin task wrapper bridging into
async code, one try/except around the whole body, a single commit on success
and on failure. All-or-nothing -- if FLAML or any baseline throws, the whole
run fails (no partial leaderboard missing a "recommended" row); no automatic
retries, same philosophy as profile_dataset.py.
"""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sklearn.pipeline import Pipeline

from app.celery_app import celery_app
from app.config import settings
from app.db import async_session_maker, engine
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.services.llm.model_interpretation_schema import ModelInterpretationResult
from app.services.llm.prompts import MODEL_INTERPRETATION_SYSTEM_PROMPT, build_model_interpretation_prompt
from app.services.llm.provider import get_llm_provider
from app.services.ml.persistence import save_model_artifact
from app.services.ml.preprocessing import build_preprocessor, get_output_feature_map, split_dtype_columns
from app.services.ml.task_mapping import to_ml_task
from app.services.ml.train import fit_all_candidates, split_and_encode
from app.services.ml.training_data import build_training_dataframe
from app.services.storage import get_storage_backend

logger = get_task_logger(__name__)

MODELS_BUCKET = "models"


@celery_app.task(
    name="train_model",
    acks_late=True,
    soft_time_limit=settings.FLAML_TIME_BUDGET_SECONDS + 120,
    time_limit=settings.FLAML_TIME_BUDGET_SECONDS + 180,
)
def train_model(model_run_id: str) -> None:
    asyncio.run(_train_model_async(model_run_id))


async def _train_model_async(model_run_id: str) -> None:
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
            logger.warning("train_model: model_run %s not found", model_run_id)
            return

        model = await db.get(Model, run.model_id)
        spec = await db.get(ModelingSpec, model.modeling_spec_id)

        try:
            ml_task = to_ml_task(spec.task_type)
            run.ml_task = ml_task

            data = await build_training_dataframe(db, spec)
            split = split_and_encode(data, spec, ml_task)

            numeric_cols, categorical_cols = split_dtype_columns(data.feature_dtypes)
            preprocessor = build_preprocessor(numeric_cols, categorical_cols)
            preprocessor.fit(split.X_train)
            output_feature_map = get_output_feature_map(preprocessor, numeric_cols, categorical_cols)

            Xt_train = preprocessor.transform(split.X_train)
            Xt_test = preprocessor.transform(split.X_test)

            candidates = fit_all_candidates(
                Xt_train, split.y_train, Xt_test, split.y_test,
                ml_task, settings.FLAML_TIME_BUDGET_SECONDS, output_feature_map,
                imbalanced=split.imbalanced,
            )

            storage = get_storage_backend()
            candidate_rows: list[ModelCandidate] = []
            for candidate in candidates:
                pipeline = Pipeline([("preprocessor", preprocessor), ("estimator", candidate.estimator)])
                artifact = save_model_artifact(pipeline)
                storage_path = f"{model.organization_id}/{run.id}/{candidate.algorithm}.joblib"
                storage.upload(MODELS_BUCKET, storage_path, artifact)

                row = ModelCandidate(
                    organization_id=model.organization_id,
                    model_run_id=run.id,
                    role=candidate.role,
                    algorithm=candidate.algorithm,
                    ml_task=ml_task,
                    feature_columns=spec.candidate_features,
                    feature_dtypes=data.feature_dtypes,
                    target_column=spec.target,
                    label_classes=split.label_classes,
                    metrics=candidate.metrics,
                    feature_importance=candidate.feature_importance,
                    hyperparams=candidate.hyperparams,
                    train_time_seconds=round(candidate.train_time_seconds, 2),
                    storage_bucket=MODELS_BUCKET,
                    storage_path=storage_path,
                )
                db.add(row)
                candidate_rows.append(row)

            await db.flush()  # assign candidate ids before referencing one below

            recommended = next(c for c in candidate_rows if c.role == "recommended")
            leaderboard_payload = [
                {"algorithm": c.algorithm, "role": c.role, "metrics": c.metrics} for c in candidate_rows
            ]

            interpretation_result = await get_llm_provider().complete_structured(
                db=db,
                task_type="model_interpretation",
                organization_id=model.organization_id,
                messages=[{
                    "role": "user",
                    "content": build_model_interpretation_prompt(
                        spec, leaderboard_payload, recommended.feature_importance or []
                    ),
                }],
                output_format=ModelInterpretationResult,
                system=MODEL_INTERPRETATION_SYSTEM_PROMPT,
                trigger=f"model_run:{run.id}",
                related_table="model_runs",
                related_id=run.id,
            )
            interpretation: ModelInterpretationResult = interpretation_result.parsed

            run.interpretation_summary = interpretation.summary_text
            run.interpretation_key_drivers = [d.model_dump() for d in interpretation.key_drivers]
            run.interpretation_model = interpretation_result.model_id
            run.row_count_used = data.row_count
            run.warnings = data.warnings
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)

            model.status = "ready"
            model.active_candidate_id = recommended.id
            model.error_message = None
            await db.commit()
        except Exception as exc:  # noqa: BLE001 -- mirrors profile_dataset.py exactly
            logger.exception("train_model failed for run %s", model_run_id)
            run.status = "error"
            run.error_message = str(exc)[:500]
            run.completed_at = datetime.now(timezone.utc)
            if model is not None:
                model.status = "error"
                model.error_message = str(exc)[:500]
            await db.commit()
