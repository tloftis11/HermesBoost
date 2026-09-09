import asyncio
import uuid
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.dependencies import CurrentOrgId, DbSession
from app.models.dataset import Dataset
from app.models.dataset_series import DatasetSeries
from app.schemas.dataset import DatasetCreateResponse, DatasetOut
from app.services.hashing import sha256_hex
from app.services.storage import get_storage_backend
from app.tasks.profile_dataset import profile_dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])

BUCKET = "datasets"


@router.post("", response_model=DatasetCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_dataset(
    organization_id: CurrentOrgId,
    db: DbSession,
    file: UploadFile = File(...),
    series_id: str | None = Form(None),
    as_of_date: date | None = Form(None),
) -> DatasetCreateResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if series_id is not None:
        series = await db.get(DatasetSeries, series_id)
        if series is None or str(series.organization_id) != str(organization_id):
            raise HTTPException(status_code=404, detail="Dataset series not found")

    content_hash = sha256_hex(data)
    dataset_id = str(uuid.uuid4())
    storage_path = f"{organization_id}/{dataset_id}/{file.filename}"

    storage = get_storage_backend()
    storage.upload(BUCKET, storage_path, data)

    dataset = Dataset(
        id=dataset_id,
        organization_id=organization_id,
        name=file.filename,
        storage_bucket=BUCKET,
        storage_path=storage_path,
        content_hash=content_hash,
        size_bytes=len(data),
        status="profiling",
        series_id=series_id,
        as_of_date=as_of_date,
    )
    db.add(dataset)
    await db.commit()

    # .to_thread avoids a nested-event-loop crash: in local/test runs
    # (CELERY_TASK_ALWAYS_EAGER=true) .delay() executes the task inline, and
    # the task itself bridges into async code via asyncio.run() -- which
    # cannot be called from within this already-running request loop. A real
    # worker process has no such loop, so this is a harmless thread hop there.
    await asyncio.to_thread(profile_dataset.delay, dataset_id)

    return DatasetCreateResponse(id=dataset_id, status=dataset.status)


@router.get("", response_model=list[DatasetOut])
async def list_datasets(organization_id: CurrentOrgId, db: DbSession) -> list[DatasetOut]:
    result = await db.execute(
        select(Dataset)
        .where(Dataset.organization_id == organization_id)
        .order_by(Dataset.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: str, organization_id: CurrentOrgId, db: DbSession
) -> DatasetOut:
    dataset = await _get_org_dataset(db, dataset_id, organization_id)
    return dataset


async def _get_org_dataset(db, dataset_id: str, organization_id: str) -> Dataset:
    try:
        uuid.UUID(dataset_id)  # validate shape only; the column itself is a string
    except ValueError:
        raise HTTPException(status_code=404, detail="Dataset not found") from None

    dataset = await db.get(Dataset, dataset_id)
    if dataset is None or str(dataset.organization_id) != str(organization_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset
