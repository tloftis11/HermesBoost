from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.security import check_api_key, resolve_current_org

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_org(request: Request, db: DbSession) -> str:
    return await resolve_current_org(request, db)


CurrentOrgId = Annotated[str, Depends(get_current_org)]
ApiKey = Annotated[str, Depends(check_api_key)]
