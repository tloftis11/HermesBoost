import io


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


async def test_unknown_dataset_404s(client):
    resp = await client.get("/api/v1/datasets/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
