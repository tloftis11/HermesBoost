"""Auth resolution: AUTH_MODE=dev|supabase, plus a placeholder API-key check.

Dev mode (AUTH_MODE=dev): every request resolves to the single seeded default
organization -- no login required. This is intentional for milestone 1 (see
plan §0.1): the org-scoping plumbing underneath is real (every query filters
by organization_id), only the "who is this" step is stubbed.

Supabase mode (AUTH_MODE=supabase): the session JWT is actually verified
against SUPABASE_JWT_SECRET. Organization resolution still falls back to the
default org for now, since a user->organization membership table doesn't
exist yet in this milestone's schema -- that arrives with real multi-tenancy.
"""

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.organizations import get_default_organization_id


class CurrentUser:
    def __init__(self, user_id: str | None, email: str | None):
        self.user_id = user_id
        self.email = email


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


async def resolve_current_user(request: Request) -> CurrentUser:
    if settings.AUTH_MODE == "dev":
        return CurrentUser(user_id=None, email=None)

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    try:
        claims = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc

    return CurrentUser(user_id=claims.get("sub"), email=claims.get("email"))


async def resolve_current_org(request: Request, db: AsyncSession) -> str:
    # Both modes resolve to the single seeded org today -- see module docstring.
    # A real user -> organization membership lookup replaces this once
    # multi-tenancy is built.
    await resolve_current_user(request)
    return await get_default_organization_id(db)


async def check_api_key(request: Request) -> str:
    """Placeholder API-key auth path for future non-browser consumers.

    Not wired to any milestone-1 endpoint yet -- the design doc calls for
    API-key auth eventually, but nothing in this slice consumes it. Checks a
    single configured key rather than a real per-org api_keys table (which
    doesn't exist in this migration yet).
    """
    api_key = request.headers.get("x-api-key")
    if not api_key or not settings.INTERNAL_API_KEY or api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
    return api_key
