import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.tasks.train_model as train_model_task
from app.config import settings
from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.model import Model
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.services.profiling import profile_csv_bytes
from app.services.storage import LocalStorageBackend, set_storage_backend_for_tests
from app.tasks.train_model import _train_model_async


@pytest_asyncio.fixture
async def storage(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    set_storage_backend_for_tests(backend)
    return backend


@pytest_asyncio.fixture(autouse=True)
async def _bind_tasks_to_test_engine(test_engine, monkeypatch):
    test_session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(train_model_task, "async_session_maker", test_session_maker)


@pytest_asyncio.fixture
async def shared_dataset(db_session, default_org_id, storage, fixtures_dir) -> Dataset:
    data = (fixtures_dir / "training_sample.csv").read_bytes()
    storage.upload("datasets", f"{default_org_id}/training_sample.csv", data)
    profile_dict = profile_csv_bytes(data)

    dataset = Dataset(
        organization_id=default_org_id,
        name="training_sample.csv",
        storage_path=f"{default_org_id}/training_sample.csv",
        content_hash="sharedhash",
        row_count=profile_dict["row_count"],
        column_count=profile_dict["column_count"],
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="sharedhash",
            row_count=profile_dict["row_count"],
            column_count=profile_dict["column_count"],
            columns=profile_dict["columns"],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


async def _train_ready_model(db_session, default_org_id, spec: ModelingSpec, monkeypatch) -> Model:
    monkeypatch.setattr(settings, "FLAML_TIME_BUDGET_SECONDS", 3)

    model = Model(organization_id=default_org_id, modeling_spec_id=spec.id, status="training")
    db_session.add(model)
    await db_session.flush()
    run = ModelRun(organization_id=default_org_id, model_id=model.id, run_type="train", status="running")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    await _train_model_async(run.id)

    await db_session.refresh(model)
    assert model.status == "ready"  # sanity check the fixture itself trained successfully
    return model


@pytest_asyncio.fixture
async def probability_model(db_session, default_org_id, shared_dataset, monkeypatch) -> Model:
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=shared_dataset.id,
        status="confirmed",
        task_type="classification",
        target="label",
        candidate_features=["num_a", "num_b", "cat_c"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return await _train_ready_model(db_session, default_org_id, spec, monkeypatch)


@pytest_asyncio.fixture
async def magnitude_model(db_session, default_org_id, shared_dataset, monkeypatch) -> Model:
    # A regression target using columns already in the shared fixture --
    # feature set ["num_a"] is a subset of probability_model's
    # ["num_a", "num_b", "cat_c"], satisfying the compatible-features rule.
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=shared_dataset.id,
        status="confirmed",
        task_type="regression",
        target="num_b",
        candidate_features=["num_a"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return await _train_ready_model(db_session, default_org_id, spec, monkeypatch)


def _create_body(probability_model: Model, magnitude_model: Model, **overrides) -> dict:
    body = {
        "name": "measles hurdle risk score",
        "probability_model_id": probability_model.id,
        "magnitude_model_id": magnitude_model.id,
        "positive_label": "1",
    }
    body.update(overrides)
    return body


async def test_create_risk_score_rejects_same_model_twice(client, probability_model):
    resp = await client.post(
        "/api/v1/risk-scores",
        json=_create_body(probability_model, probability_model),
    )
    assert resp.status_code == 400
    assert "different models" in resp.json()["detail"]


async def test_create_risk_score_rejects_not_ready_model(client, db_session, default_org_id, probability_model, shared_dataset):
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=shared_dataset.id,
        status="confirmed",
        task_type="regression",
        target="num_b",
        candidate_features=["num_a"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    not_ready = Model(organization_id=default_org_id, modeling_spec_id=spec.id, status="training")
    db_session.add(not_ready)
    await db_session.commit()
    await db_session.refresh(not_ready)

    resp = await client.post(
        "/api/v1/risk-scores",
        json=_create_body(probability_model, not_ready),
    )
    assert resp.status_code == 400
    assert "ready" in resp.json()["detail"]


async def test_create_risk_score_rejects_wrong_task_pairing(client, probability_model, magnitude_model):
    # Swapped: probability_model_id must be a classifier, magnitude_model_id a regressor.
    resp = await client.post(
        "/api/v1/risk-scores",
        json=_create_body(magnitude_model, probability_model, positive_label="1"),
    )
    assert resp.status_code == 400
    assert "classification" in resp.json()["detail"]


async def test_create_risk_score_rejects_bad_positive_label(client, probability_model, magnitude_model):
    resp = await client.post(
        "/api/v1/risk-scores",
        json=_create_body(probability_model, magnitude_model, positive_label="nope"),
    )
    assert resp.status_code == 400
    assert "nope" in resp.json()["detail"]


async def test_create_risk_score_rejects_incompatible_features(
    client, db_session, default_org_id, probability_model, shared_dataset, monkeypatch
):
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=shared_dataset.id,
        status="confirmed",
        task_type="regression",
        target="num_b",
        candidate_features=["cat_c"],  # fine on its own, but we'll rename below to force a mismatch
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    incompatible = await _train_ready_model(db_session, default_org_id, spec, monkeypatch)

    # Simulate a candidate that used a feature the probability model doesn't have.
    from app.models.model_candidate import ModelCandidate

    candidate = await db_session.get(ModelCandidate, incompatible.active_candidate_id)
    candidate.feature_columns = ["totally_unrelated_column"]
    await db_session.commit()

    resp = await client.post(
        "/api/v1/risk-scores",
        json=_create_body(probability_model, incompatible),
    )
    assert resp.status_code == 400
    assert "totally_unrelated_column" in resp.json()["detail"]


async def test_create_list_and_get_risk_score(client, probability_model, magnitude_model):
    create_resp = await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "measles hurdle risk score"
    assert created["positive_label"] == "1"

    list_resp = await client.get("/api/v1/risk-scores")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = await client.get(f"/api/v1/risk-scores/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]


async def test_get_risk_scores_computes_product_and_covers_all_entities(client, probability_model, magnitude_model):
    created = (
        await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    ).json()

    resp = await client.get(f"/api/v1/risk-scores/{created['id']}/scores")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_row_count"] == 90  # training_sample.csv's full row count
    rows = body["rows"]
    assert len(rows) == 90
    for row in rows:
        assert row["risk_score"] == row["probability"] * row["predicted_magnitude"]
        assert 0.0 <= row["probability"] <= 1.0

    # Sorted descending by risk score.
    scores = [r["risk_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


async def test_get_risk_scores_entity_id_filter(client, probability_model, magnitude_model):
    created = (
        await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    ).json()

    resp = await client.get(f"/api/v1/risk-scores/{created['id']}/scores", params={"entity_id": "1"})
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "1"


async def test_get_risk_scores_csv_format(client, probability_model, magnitude_model):
    created = (
        await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    ).json()

    resp = await client.get(f"/api/v1/risk-scores/{created['id']}/scores", params={"format": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    lines = resp.text.strip().splitlines()
    assert lines[0] == "entity_id,score_date,probability,predicted_magnitude,risk_score"
    assert len(lines) == 91  # header + 90 rows


async def test_get_risk_scores_with_valid_api_key(client, probability_model, magnitude_model):
    created = (
        await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    ).json()
    key = (await client.post("/api/v1/api-keys", json={"name": "external"})).json()

    resp = await client.get(
        f"/api/v1/risk-scores/{created['id']}/scores", headers={"x-api-key": key["raw_key"]}
    )
    assert resp.status_code == 200
    assert resp.json()["total_row_count"] == 90


async def test_get_risk_scores_with_invalid_api_key_401s(client, probability_model, magnitude_model):
    created = (
        await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    ).json()

    resp = await client.get(f"/api/v1/risk-scores/{created['id']}/scores", headers={"x-api-key": "bogus"})
    assert resp.status_code == 401


async def test_delete_risk_score(client, probability_model, magnitude_model):
    created = (
        await client.post("/api/v1/risk-scores", json=_create_body(probability_model, magnitude_model))
    ).json()

    del_resp = await client.delete(f"/api/v1/risk-scores/{created['id']}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/risk-scores/{created['id']}")
    assert get_resp.status_code == 404
