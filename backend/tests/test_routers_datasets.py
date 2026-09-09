import io
import uuid

from app.models.dataset import Dataset


async def test_upload_and_list_dataset(client):
    csv_bytes = b"a,b\n1,2\n3,4\n"
    files = {"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")}
    resp = await client.post("/api/v1/datasets", files=files)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "profiling"
    dataset_id = body["id"]

    list_resp = await client.get("/api/v1/datasets")
    assert list_resp.status_code == 200
    datasets = list_resp.json()
    assert any(d["id"] == dataset_id for d in datasets)

    get_resp = await client.get(f"/api/v1/datasets/{dataset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "test.csv"


async def test_profile_pending_before_worker_runs(client):
    # profile_dataset.delay is stubbed to a no-op in the client fixture, so
    # the dataset never transitions past 'profiling' here -- this is
    # deliberately testing the polling shape, not the worker itself.
    csv_bytes = b"a,b\n1,2\n"
    files = {"file": ("pending.csv", io.BytesIO(csv_bytes), "text/csv")}
    resp = await client.post("/api/v1/datasets", files=files)
    dataset_id = resp.json()["id"]

    profile_resp = await client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert profile_resp.status_code == 200
    assert profile_resp.json()["status"] == "profiling"


async def test_rejects_non_csv(client):
    files = {"file": ("data.txt", io.BytesIO(b"not a csv"), "text/plain")}
    resp = await client.post("/api/v1/datasets", files=files)
    assert resp.status_code == 400


async def test_rejects_empty_file(client):
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    resp = await client.post("/api/v1/datasets", files=files)
    assert resp.status_code == 400


async def _make_staged_dataset(db_session, default_org_id) -> Dataset:
    dataset = Dataset(
        organization_id=default_org_id,
        name="staged.csv",
        storage_path=f"{default_org_id}/x/staged.csv",
        content_hash="stagedhash",
        status="uploaded",
        pending_confirmation=True,
        source_url="https://example.com/staged.csv",
    )
    db_session.add(dataset)
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


async def test_confirm_staged_dataset_starts_profiling(client, db_session, default_org_id):
    dataset = await _make_staged_dataset(db_session, default_org_id)

    resp = await client.post(f"/api/v1/datasets/{dataset.id}/confirm")
    assert resp.status_code == 202
    assert resp.json()["status"] == "profiling"

    get_resp = await client.get(f"/api/v1/datasets/{dataset.id}")
    assert get_resp.json()["pending_confirmation"] is False
    assert get_resp.json()["status"] == "profiling"


async def test_confirm_non_pending_dataset_400s(client):
    csv_bytes = b"a,b\n1,2\n"
    files = {"file": ("normal.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_resp = await client.post("/api/v1/datasets", files=files)
    dataset_id = upload_resp.json()["id"]

    resp = await client.post(f"/api/v1/datasets/{dataset_id}/confirm")
    assert resp.status_code == 400


async def test_delete_dataset(client, db_session, default_org_id):
    dataset = await _make_staged_dataset(db_session, default_org_id)

    resp = await client.delete(f"/api/v1/datasets/{dataset.id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/datasets/{dataset.id}")
    assert get_resp.status_code == 404


async def test_unknown_dataset_404s(client):
    resp = await client.get("/api/v1/datasets/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_create_and_list_dataset_series(client):
    create_resp = await client.post("/api/v1/dataset-series", json={"name": "daily_counts"})
    assert create_resp.status_code == 201
    assert create_resp.json()["name"] == "daily_counts"

    list_resp = await client.get("/api/v1/dataset-series")
    assert list_resp.status_code == 200
    assert [s["name"] for s in list_resp.json()] == ["daily_counts"]


async def test_create_dataset_series_rejects_duplicate_name(client):
    await client.post("/api/v1/dataset-series", json={"name": "daily_counts"})
    resp = await client.post("/api/v1/dataset-series", json={"name": "daily_counts"})
    assert resp.status_code == 409


async def test_upload_dataset_tagged_into_series(client):
    series_resp = await client.post("/api/v1/dataset-series", json={"name": "daily_counts"})
    series_id = series_resp.json()["id"]

    csv_bytes = b"a,b\n1,2\n3,4\n"
    files = {"file": ("day1.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_resp = await client.post(
        "/api/v1/datasets", files=files, data={"series_id": series_id, "as_of_date": "2026-09-09"}
    )
    assert upload_resp.status_code == 202
    dataset_id = upload_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/datasets/{dataset_id}")
    assert get_resp.json()["series_id"] == series_id
    assert get_resp.json()["as_of_date"] == "2026-09-09"


async def test_upload_dataset_rejects_unknown_series(client):
    csv_bytes = b"a,b\n1,2\n"
    files = {"file": ("day1.csv", io.BytesIO(csv_bytes), "text/csv")}
    resp = await client.post(
        "/api/v1/datasets", files=files, data={"series_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404
