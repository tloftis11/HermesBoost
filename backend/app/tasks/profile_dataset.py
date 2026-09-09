"""Celery task: profile an uploaded dataset and generate its LLM description.

Runs in the worker, never in the request cycle. Caching by content hash: if
another dataset in this org already has a profile for the same content_hash,
reuse it instead of re-scanning with DuckDB or re-billing the LLM -- this is
why dataset_profiles has a unique (organization_id, content_hash) constraint
rather than being keyed 1:1 on dataset_id.
"""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import async_session_maker
from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.services import profiling
from app.services.llm.prompts import (
    DATASET_DESCRIPTION_SYSTEM_PROMPT,
    build_dataset_description_prompt,
)
from app.services.llm.provider import get_llm_provider
from app.services.storage import get_storage_backend

logger = get_task_logger(__name__)


@celery_app.task(name="profile_dataset", acks_late=True)
def profile_dataset(dataset_id: str) -> None:
    asyncio.run(_profile_dataset_async(dataset_id))


async def _profile_dataset_async(dataset_id: str) -> None:
    async with async_session_maker() as db:
        dataset = await db.get(Dataset, dataset_id)
        if dataset is None:
            logger.warning("profile_dataset: dataset %s not found", dataset_id)
            return

        try:
            existing_profile = await _find_existing_profile(db, dataset)

            if existing_profile is not None:
                dataset.row_count = existing_profile.row_count
                dataset.column_count = existing_profile.column_count
            else:
                storage = get_storage_backend()
                raw_bytes = storage.download(dataset.storage_bucket, dataset.storage_path)

                profile = profiling.profile_csv_bytes(raw_bytes)
                prompt = build_dataset_description_prompt(
                    profile, profiling.sample_rows(raw_bytes)
                )
                result = await get_llm_provider().complete(
                    db=db,
                    task_type="dataset_description",
                    organization_id=str(dataset.organization_id),
                    prompt=prompt,
                    system=DATASET_DESCRIPTION_SYSTEM_PROMPT,
                    trigger=f"dataset_upload:{dataset_id}",
                    related_table="datasets",
                    related_id=dataset_id,
                )

                db.add(
                    DatasetProfile(
                        organization_id=dataset.organization_id,
                        dataset_id=dataset.id,
                        content_hash=dataset.content_hash,
                        row_count=profile["row_count"],
                        column_count=profile["column_count"],
                        columns=profile["columns"],
                        ai_description=result.text,
                        ai_description_model=result.model_id,
                        ai_description_generated_at=datetime.now(timezone.utc),
                    )
                )
                dataset.row_count = profile["row_count"]
                dataset.column_count = profile["column_count"]

            dataset.status = "profiled"
            await db.commit()
        except Exception as exc:  # noqa: BLE001 -- a single bad file must not retry forever
            logger.exception("profile_dataset failed for %s", dataset_id)
            dataset.status = "error"
            dataset.error_message = str(exc)[:500]
            await db.commit()


async def _find_existing_profile(db, dataset: Dataset) -> DatasetProfile | None:
    result = await db.execute(
        select(DatasetProfile).where(
            DatasetProfile.organization_id == dataset.organization_id,
            DatasetProfile.content_hash == dataset.content_hash,
        )
    )
    return result.scalar_one_or_none()
