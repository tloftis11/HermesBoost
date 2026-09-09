import uuid

import pytest_asyncio

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile


@pytest_asyncio.fixture
async def profiled_dataset(db_session, default_org_id) -> Dataset:
    dataset = Dataset(
        organization_id=default_org_id,
        name="types_sample.csv",
        storage_path=f"{default_org_id}/x/types_sample.csv",
        content_hash="testhash123",
        row_count=6,
        column_count=3,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="testhash123",
            row_count=6,
            column_count=3,
            columns=[
                {"name": "row_id", "dtype": "id"},
                {"name": "amount", "dtype": "numeric"},
                {"name": "category", "dtype": "categorical"},
            ],
            ai_description="A fake profiled dataset for tests.",
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


async def test_create_modeling_spec_requires_profiled_dataset(client, db_session, default_org_id):
    dataset = Dataset(
        organization_id=default_org_id,
        name="still_profiling.csv",
        storage_path=f"{default_org_id}/y/still_profiling.csv",
        content_hash="otherhash",
        status="profiling",
    )
    db_session.add(dataset)
    await db_session.commit()

    resp = await client.post(f"/api/v1/datasets/{dataset.id}/modeling-specs")
    assert resp.status_code == 400


async def test_create_and_get_modeling_spec(client, profiled_dataset):
    resp = await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")
    assert resp.status_code == 201
    spec = resp.json()
    assert spec["status"] == "draft"
    assert spec["candidate_features"] == []
    assert spec["retrain_cadence"] == "weekly"
    assert spec["score_cadence"] == "daily"

    detail_resp = await client.get(f"/api/v1/modeling-specs/{spec['id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["spec"]["id"] == spec["id"]
    assert detail["messages"] == []


async def test_send_message_persists_and_updates_spec(client, profiled_dataset):
    create_resp = await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")
    spec_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/modeling-specs/{spec_id}/messages", json={"message": "Score risk for this data"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Fake reply" in body["reply_message"]
    assert body["spec"]["task_type"] == "classification"  # fake provider's default spec

    detail = (await client.get(f"/api/v1/modeling-specs/{spec_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "Score risk for this data"
    assert detail["messages"][1]["content"] == body["reply_message"]


async def test_send_message_twice_keeps_history(client, profiled_dataset):
    create_resp = await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")
    spec_id = create_resp.json()["id"]

    await client.post(f"/api/v1/modeling-specs/{spec_id}/messages", json={"message": "first"})
    await client.post(f"/api/v1/modeling-specs/{spec_id}/messages", json={"message": "second"})

    detail = (await client.get(f"/api/v1/modeling-specs/{spec_id}")).json()
    assert len(detail["messages"]) == 4
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]


async def test_patch_modeling_spec_updates_features_and_cadence(client, profiled_dataset):
    create_resp = await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")
    spec_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/modeling-specs/{spec_id}",
        json={"candidate_features": ["amount", "category"], "retrain_cadence": "monthly"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_features"] == ["amount", "category"]
    assert body["retrain_cadence"] == "monthly"
    assert body["score_cadence"] == "daily"  # untouched field unchanged


async def test_unknown_modeling_spec_404s(client):
    resp = await client.get(f"/api/v1/modeling-specs/{uuid.uuid4()}")
    assert resp.status_code == 404
