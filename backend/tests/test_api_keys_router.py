import uuid


async def test_create_api_key_returns_raw_key_once(client):
    resp = await client.post("/api/v1/api-keys", json={"name": "CI pipeline"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "CI pipeline"
    assert body["raw_key"].startswith("hb_live_")
    assert body["key_prefix"] == body["raw_key"][:12]
    assert body["revoked_at"] is None


async def test_list_api_keys_never_returns_raw_key(client):
    await client.post("/api/v1/api-keys", json={"name": "CI pipeline"})
    resp = await client.get("/api/v1/api-keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 1
    assert "raw_key" not in keys[0]
    assert keys[0]["name"] == "CI pipeline"


async def test_revoke_api_key(client):
    created = (await client.post("/api/v1/api-keys", json={"name": "temp"})).json()

    revoke_resp = await client.delete(f"/api/v1/api-keys/{created['id']}")
    assert revoke_resp.status_code == 204

    list_resp = await client.get("/api/v1/api-keys")
    assert list_resp.json()[0]["revoked_at"] is not None


async def test_revoke_unknown_api_key_404s(client):
    resp = await client.delete(f"/api/v1/api-keys/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_revoked_api_key_rejected_by_scores_endpoint(client, db_session, default_org_id):
    from app.models.dataset import Dataset
    from app.models.dataset_profile import DatasetProfile
    from app.models.model import Model
    from app.models.modeling_spec import ModelingSpec

    dataset = Dataset(
        organization_id=default_org_id, name="d.csv", storage_path=f"{default_org_id}/d.csv",
        content_hash="h", row_count=1, column_count=1, status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(DatasetProfile(
        organization_id=default_org_id, dataset_id=dataset.id, content_hash="h",
        row_count=1, column_count=1, columns=[],
    ))
    spec = ModelingSpec(organization_id=default_org_id, dataset_id=dataset.id, status="confirmed")
    db_session.add(spec)
    await db_session.flush()
    model = Model(organization_id=default_org_id, modeling_spec_id=spec.id, status="ready")
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    created = (await client.post("/api/v1/api-keys", json={"name": "temp"})).json()
    raw_key = created["raw_key"]
    await client.delete(f"/api/v1/api-keys/{created['id']}")

    resp = await client.get(f"/api/v1/models/{model.id}/scores", headers={"x-api-key": raw_key})
    assert resp.status_code == 401
