from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.security import resolve_current_org, resolve_org_any_auth

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_org(request: Request, db: DbSession) -> str:
    return await resolve_current_org(request, db)


async def get_org_any_auth(request: Request, db: DbSession) -> str:
    return await resolve_org_any_auth(request, db)


CurrentOrgId = Annotated[str, Depends(get_current_org)]

# Dual-auth: an X-API-Key header (external callers) or the existing
# dev-mode/session path (the browser frontend). Only used where an
# endpoint is meant to also serve non-browser API-key consumers.
OrgIdAnyAuth = Annotated[str, Depends(get_org_any_auth)]
