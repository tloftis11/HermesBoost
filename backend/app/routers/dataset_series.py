from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentOrgId, DbSession
from app.models.dataset_series import DatasetSeries
from app.schemas.dataset import DatasetSeriesCreate, DatasetSeriesOut

router = APIRouter(tags=["dataset-series"])


@router.get("/dataset-series", response_model=list[DatasetSeriesOut])
async def list_dataset_series(organization_id: CurrentOrgId, db: DbSession) -> list[DatasetSeriesOut]:
    result = await db.execute(
        select(DatasetSeries)
        .where(DatasetSeries.organization_id == organization_id)
        .order_by(DatasetSeries.name)
    )
    return list(result.scalars().all())


@router.post("/dataset-series", response_model=DatasetSeriesOut, status_code=201)
async def create_dataset_series(
    body: DatasetSeriesCreate, organization_id: CurrentOrgId, db: DbSession
) -> DatasetSeriesOut:
    existing = await db.execute(
        select(DatasetSeries).where(
            DatasetSeries.organization_id == organization_id, DatasetSeries.name == body.name
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"A series named '{body.name}' already exists.")

    series = DatasetSeries(organization_id=organization_id, name=body.name)
    db.add(series)
    await db.commit()
    await db.refresh(series)
    return series
