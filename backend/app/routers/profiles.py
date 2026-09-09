from fastapi import APIRouter

from app.dependencies import CurrentOrgId, DbSession
from app.routers.datasets import _get_org_dataset
from app.schemas.profile import DatasetProfileOut
from app.services.dataset_profiles import get_latest_profile

router = APIRouter(prefix="/datasets", tags=["profiles"])


@router.get("/{dataset_id}/profile", response_model=DatasetProfileOut)
async def get_profile(
    dataset_id: str, organization_id: CurrentOrgId, db: DbSession
) -> DatasetProfileOut:
    dataset = await _get_org_dataset(db, dataset_id, organization_id)

    if dataset.status == "error":
        return DatasetProfileOut(status="error", error_message=dataset.error_message)

    if dataset.status != "profiled":
        # 200, not 404 -- the frontend polls this while the worker runs.
        return DatasetProfileOut(status="profiling")

    profile = await get_latest_profile(db, dataset)
    if profile is None:
        # Shouldn't happen once status == 'profiled', but don't 500 if it does.
        return DatasetProfileOut(status="profiling")

    return DatasetProfileOut(
        status="profiled",
        row_count=profile.row_count,
        column_count=profile.column_count,
        columns=profile.columns,
        ai_description=profile.ai_description,
        ai_description_model=profile.ai_description_model,
        profiled_at=profile.profiled_at,
    )
