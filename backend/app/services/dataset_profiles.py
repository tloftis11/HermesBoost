from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile


async def get_latest_profile(db: AsyncSession, dataset: Dataset) -> DatasetProfile | None:
    """The (organization_id, content_hash) lookup shared by the profile
    endpoint and the intent-chat endpoint -- a dataset_profiles row is keyed
    by content hash, not dataset_id, so multiple datasets with identical
    content share one profile (see tasks/profile_dataset.py's cache-by-hash
    logic)."""
    result = await db.execute(
        select(DatasetProfile).where(
            DatasetProfile.organization_id == dataset.organization_id,
            DatasetProfile.content_hash == dataset.content_hash,
        )
    )
    return result.scalar_one_or_none()
