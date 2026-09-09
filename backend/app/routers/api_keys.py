import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import CurrentOrgId, DbSession
from app.models.api_key import ApiKey
from app.services.api_keys import generate_api_key

router = APIRouter(tags=["api-keys"])


class ApiKeyCreateRequest(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyCreatedOut(ApiKeyOut):
    raw_key: str


@router.post("/api-keys", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest, organization_id: CurrentOrgId, db: DbSession
) -> ApiKeyCreatedOut:
    raw_key, key_prefix, key_hash = generate_api_key()

    row = ApiKey(organization_id=organization_id, name=body.name, key_prefix=key_prefix, key_hash=key_hash)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # raw_key appears in this response only -- it is never stored and can
    # never be shown again after this call returns.
    return ApiKeyCreatedOut(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(organization_id: CurrentOrgId, db: DbSession) -> list[ApiKeyOut]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.organization_id == organization_id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, organization_id: CurrentOrgId, db: DbSession) -> None:
    try:
        uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="API key not found") from None

    row = await db.get(ApiKey, key_id)
    if row is None or str(row.organization_id) != str(organization_id):
        raise HTTPException(status_code=404, detail="API key not found")

    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
