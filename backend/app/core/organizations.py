from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization

DEFAULT_ORG_SLUG = "default"

_default_org_id_cache: str | None = None


async def get_default_organization_id(db: AsyncSession) -> str:
    """Resolve the id of the single seeded organization used in dev-auth mode.

    Cached in-process since this row is essentially static for the life of
    the alpha (single-tenant today, per the design doc's multi-tenant-ready
    schema decision).
    """
    global _default_org_id_cache
    if _default_org_id_cache is not None:
        return _default_org_id_cache

    result = await db.execute(
        select(Organization.id).where(Organization.slug == DEFAULT_ORG_SLUG)
    )
    org_id = result.scalar_one()
    _default_org_id_cache = str(org_id)
    return _default_org_id_cache
