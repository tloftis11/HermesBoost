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


async def test_patch_modeling_spec_sets_entity_id_column(client, profiled_dataset):
    create_resp = await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")
    spec_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/modeling-specs/{spec_id}", json={"entity_id_column": "row_id"}
    )
    assert resp.status_code == 200
    assert resp.json()["entity_id_column"] == "row_id"

    detail = (await client.get(f"/api/v1/modeling-specs/{spec_id}")).json()
    assert detail["spec"]["entity_id_column"] == "row_id"


async def test_chat_flow_persists_entity_id_column_from_carried_forward_spec(
    client, db_session, default_org_id, profiled_dataset
):
    # The fake provider's DEFAULT_FAKE_SPEC has no entity_id_column, but it
    # carries forward whatever the most recent assistant turn's spec was --
    # seed one directly to exercise that persistence path without touching
    # the fake provider itself.
    from app.models.chat_message import ChatMessage
    from app.services.llm.modeling_spec_schema import ChatTurnResponse, ModelingSpecFields

    create_resp = await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")
    spec_id = create_resp.json()["id"]

    seeded = ChatTurnResponse(
        reply_message="seed",
        modeling_spec=ModelingSpecFields(
            task_type="classification",
            task_description="seeded",
            target="category",
            candidate_features=["amount"],
            evaluation_metric="accuracy",
            entity_id_column="row_id",
            retrain_cadence="weekly",
            score_cadence="daily",
        ),
    )
    db_session.add(
        ChatMessage(
            organization_id=default_org_id,
            modeling_spec_id=spec_id,
            role="assistant",
            content=seeded.model_dump_json(),
        )
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/modeling-specs/{spec_id}/messages", json={"message": "keep going"}
    )
    assert resp.status_code == 200
    assert resp.json()["spec"]["entity_id_column"] == "row_id"


async def test_unknown_modeling_spec_404s(client):
    resp = await client.get(f"/api/v1/modeling-specs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest_asyncio.fixture
async def joinable_dataset(db_session, default_org_id) -> Dataset:
    """A second profiled dataset sharing 'row_id' with profiled_dataset,
    plus its own 'population' column, for join-dataset tests."""
    dataset = Dataset(
        organization_id=default_org_id,
        name="region_stats.csv",
        storage_path=f"{default_org_id}/z/region_stats.csv",
        content_hash="joinhash456",
        row_count=6,
        column_count=2,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="joinhash456",
            row_count=6,
            column_count=2,
            columns=[
                {"name": "row_id", "dtype": "id"},
                {"name": "population", "dtype": "numeric"},
            ],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


async def test_attach_join_dataset(client, profiled_dataset, joinable_dataset):
    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]

    resp = await client.post(
        f"/api/v1/modeling-specs/{spec_id}/join-datasets",
        json={"dataset_id": joinable_dataset.id, "join_key_column": "row_id", "join_type": "left"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["dataset_id"] == joinable_dataset.id
    assert body["dataset_name"] == "region_stats.csv"
    assert body["join_key_column"] == "row_id"
    assert body["join_type"] == "left"

    list_resp = await client.get(f"/api/v1/modeling-specs/{spec_id}/join-datasets")
    assert list_resp.status_code == 200
    assert [j["id"] for j in list_resp.json()] == [body["id"]]


async def test_attach_join_dataset_rejects_base_dataset_as_target(client, profiled_dataset):
    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]

    resp = await client.post(
        f"/api/v1/modeling-specs/{spec_id}/join-datasets",
        json={"dataset_id": profiled_dataset.id, "join_key_column": "row_id"},
    )
    assert resp.status_code == 400


async def test_attach_join_dataset_rejects_duplicate(client, profiled_dataset, joinable_dataset):
    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]
    body = {"dataset_id": joinable_dataset.id, "join_key_column": "row_id"}

    first = await client.post(f"/api/v1/modeling-specs/{spec_id}/join-datasets", json=body)
    assert first.status_code == 201

    second = await client.post(f"/api/v1/modeling-specs/{spec_id}/join-datasets", json=body)
    assert second.status_code == 400


async def test_attach_join_dataset_rejects_missing_join_key(client, profiled_dataset, joinable_dataset):
    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]

    resp = await client.post(
        f"/api/v1/modeling-specs/{spec_id}/join-datasets",
        json={"dataset_id": joinable_dataset.id, "join_key_column": "not_a_real_column"},
    )
    assert resp.status_code == 400


async def test_attach_join_dataset_rejects_unprofiled_dataset(client, db_session, default_org_id, profiled_dataset):
    unprofiled = Dataset(
        organization_id=default_org_id,
        name="still_profiling.csv",
        storage_path=f"{default_org_id}/w/still_profiling.csv",
        content_hash="unprofiledhash",
        status="profiling",
    )
    db_session.add(unprofiled)
    await db_session.commit()

    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]
    resp = await client.post(
        f"/api/v1/modeling-specs/{spec_id}/join-datasets",
        json={"dataset_id": unprofiled.id, "join_key_column": "row_id"},
    )
    assert resp.status_code == 400


async def test_detach_join_dataset(client, profiled_dataset, joinable_dataset):
    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]
    join_id = (
        await client.post(
            f"/api/v1/modeling-specs/{spec_id}/join-datasets",
            json={"dataset_id": joinable_dataset.id, "join_key_column": "row_id"},
        )
    ).json()["id"]

    delete_resp = await client.delete(f"/api/v1/modeling-specs/{spec_id}/join-datasets/{join_id}")
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/modeling-specs/{spec_id}/join-datasets")
    assert list_resp.json() == []


async def test_detach_unknown_join_dataset_404s(client, profiled_dataset):
    spec_id = (await client.post(f"/api/v1/datasets/{profiled_dataset.id}/modeling-specs")).json()["id"]
    resp = await client.delete(f"/api/v1/modeling-specs/{spec_id}/join-datasets/{uuid.uuid4()}")
    assert resp.status_code == 404
