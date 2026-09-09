"""Auth resolution: AUTH_MODE=dev|supabase for the browser frontend, plus a
real per-organization API-key path for external/non-browser consumers.

Dev mode (AUTH_MODE=dev): every request resolves to the single seeded default
organization -- no login required. This is intentional for milestone 1 (see
plan §0.1): the org-scoping plumbing underneath is real (every query filters
by organization_id), only the "who is this" step is stubbed.

Supabase mode (AUTH_MODE=supabase): the session JWT is actually verified
against SUPABASE_JWT_SECRET. Organization resolution still falls back to the
default org for now, since a user->organization membership table doesn't
exist yet in this milestone's schema -- that arrives with real multi-tenancy.

API keys (milestone 6): a real, hashed, revocable, per-org api_keys table,
checked via the X-API-Key header -- deliberately not Authorization: Bearer,
to avoid colliding with the Supabase session-JWT bearer convention above.
"""

from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.organizations import get_default_organization_id
from app.models.api_key import ApiKey
from app.services.hashing import sha256_hex


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


async def resolve_org_from_api_key(request: Request, db: AsyncSession) -> str:
    """Resolves an organization from a real X-API-Key header, checked
    against the hashed, revocable api_keys table. Raises 401 on anything
    missing/invalid/revoked -- an external caller that sent a bad key
    should never silently fall through to some default."""
    raw_key = request.headers.get("x-api-key")
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    key_hash = sha256_hex(raw_key.encode())
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")

    row.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return row.organization_id


async def resolve_org_any_auth(request: Request, db: AsyncSession) -> str:
    """Dual-auth: an X-API-Key header (external callers) takes priority and
    must be valid; otherwise falls back to the existing dev-mode/session
    path (the browser frontend, which never sends that header)."""
    if request.headers.get("x-api-key"):
        return await resolve_org_from_api_key(request, db)
    return await resolve_current_org(request, db)
