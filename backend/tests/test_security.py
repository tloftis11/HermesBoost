from unittest.mock import MagicMock

import pytest

from app.security import resolve_org_any_auth, resolve_org_from_api_key
from app.services.api_keys import generate_api_key


def _request_with_headers(headers: dict) -> MagicMock:
    request = MagicMock()
    request.headers = headers
    return request


@pytest.fixture
async def api_key_row(db_session, default_org_id):
    from app.models.api_key import ApiKey

    raw_key, prefix, key_hash = generate_api_key()
    row = ApiKey(organization_id=default_org_id, name="test key", key_prefix=prefix, key_hash=key_hash)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return raw_key, row


async def test_resolve_org_from_api_key_valid(db_session, default_org_id, api_key_row):
    raw_key, _row = api_key_row
    request = _request_with_headers({"x-api-key": raw_key})

    org_id = await resolve_org_from_api_key(request, db_session)
    assert org_id == default_org_id


async def test_resolve_org_from_api_key_missing_header(db_session):
    from fastapi import HTTPException

    request = _request_with_headers({})
    with pytest.raises(HTTPException) as exc_info:
        await resolve_org_from_api_key(request, db_session)
    assert exc_info.value.status_code == 401


async def test_resolve_org_from_api_key_invalid_key(db_session):
    from fastapi import HTTPException

    request = _request_with_headers({"x-api-key": "hb_live_totally-not-a-real-key"})
    with pytest.raises(HTTPException) as exc_info:
        await resolve_org_from_api_key(request, db_session)
    assert exc_info.value.status_code == 401


async def test_resolve_org_from_api_key_revoked(db_session, default_org_id, api_key_row):
    from datetime import datetime, timezone

    raw_key, row = api_key_row
    row.revoked_at = datetime.now(timezone.utc)
    await db_session.commit()

    from fastapi import HTTPException

    request = _request_with_headers({"x-api-key": raw_key})
    with pytest.raises(HTTPException) as exc_info:
        await resolve_org_from_api_key(request, db_session)
    assert exc_info.value.status_code == 401


async def test_resolve_org_from_api_key_updates_last_used_at(db_session, api_key_row):
    raw_key, row = api_key_row
    assert row.last_used_at is None

    request = _request_with_headers({"x-api-key": raw_key})
    await resolve_org_from_api_key(request, db_session)

    await db_session.refresh(row)
    assert row.last_used_at is not None


async def test_resolve_org_any_auth_uses_api_key_when_present(db_session, default_org_id, api_key_row):
    raw_key, _row = api_key_row
    request = _request_with_headers({"x-api-key": raw_key})

    org_id = await resolve_org_any_auth(request, db_session)
    assert org_id == default_org_id


async def test_resolve_org_any_auth_falls_back_to_session_when_no_key(db_session, default_org_id):
    request = _request_with_headers({})
    org_id = await resolve_org_any_auth(request, db_session)
    assert org_id == default_org_id


async def test_resolve_org_any_auth_rejects_bad_key_rather_than_falling_back(db_session):
    from fastapi import HTTPException

    request = _request_with_headers({"x-api-key": "not-a-real-key"})
    with pytest.raises(HTTPException) as exc_info:
        await resolve_org_any_auth(request, db_session)
    assert exc_info.value.status_code == 401
