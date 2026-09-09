import uuid
from decimal import Decimal

import pytest_asyncio

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec


@pytest_asyncio.fixture
async def confirmed_spec(db_session, default_org_id) -> ModelingSpec:
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
        )
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="category",
        candidate_features=["amount"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


async def test_build_model_creates_training_row(client, confirmed_spec):
    resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    assert resp.status_code == 202
    body = resp.json()
    assert uuid.UUID(body["model_id"])
    assert uuid.UUID(body["model_run_id"])

    get_resp = await client.get(f"/api/v1/models/{body['model_id']}")
    assert get_resp.status_code == 200
    guided = get_resp.json()
    assert guided["status"] == "training"
    assert guided["active_candidate"] is None
    assert guided["latest_run"]["status"] == "running"


async def test_build_model_rejects_unsupported_task_type(client, confirmed_spec, db_session):
    confirmed_spec.task_type = "clustering"
    await db_session.commit()

    resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    assert resp.status_code == 400
    assert "not supported" in resp.json()["detail"]


async def test_build_model_reuses_existing_model_slot_on_retrain(client, confirmed_spec):
    first = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    second = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")

    assert first.json()["model_id"] == second.json()["model_id"]
    assert first.json()["model_run_id"] != second.json()["model_run_id"]


async def test_get_model_for_spec_404s_before_first_build(client, confirmed_spec):
    resp = await client.get(f"/api/v1/modeling-specs/{confirmed_spec.id}/models")
    assert resp.status_code == 404


async def test_unknown_model_404s(client):
    resp = await client.get(f"/api/v1/models/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest_asyncio.fixture
async def completed_model_with_leaderboard(db_session, default_org_id, confirmed_spec):
    model = Model(organization_id=default_org_id, modeling_spec_id=confirmed_spec.id, status="training")
    db_session.add(model)
    await db_session.flush()

    run = ModelRun(
        organization_id=default_org_id,
        model_id=model.id,
        run_type="train",
        status="completed",
        ml_task="classification",
        row_count_used=6,
        warnings=[],
        interpretation_summary="A plain-English summary.",
        interpretation_key_drivers=[{"feature": "amount", "plain_description": "matters", "relative_importance": 1.0}],
        interpretation_model="fake-model",
    )
    db_session.add(run)
    await db_session.flush()

    def _make_candidate(role: str, algorithm: str) -> ModelCandidate:
        return ModelCandidate(
            organization_id=default_org_id,
            model_run_id=run.id,
            role=role,
            algorithm=algorithm,
            ml_task="classification",
            feature_columns=["amount"],
            feature_dtypes={"amount": "numeric"},
            target_column="category",
            label_classes=["A", "B", "C"],
            metrics={"auc": 0.8, "precision": 0.7, "recall": 0.6, "accuracy": 0.75, "calibration_error": 0.05},
            feature_importance=[{"feature": "amount", "importance": 1.0}],
            hyperparams={"max_iter": 1000},
            train_time_seconds=Decimal("1.23"),
            storage_bucket="models",
            storage_path=f"{default_org_id}/{run.id}/{algorithm}.joblib",
        )

    recommended = _make_candidate("recommended", "flaml_lgbm")
    baselines = [
        _make_candidate("baseline", "logistic_regression"),
        _make_candidate("baseline", "random_forest"),
        _make_candidate("baseline", "xgboost"),
    ]
    db_session.add_all([recommended, *baselines])
    await db_session.flush()

    model.status = "ready"
    model.active_candidate_id = recommended.id
    await db_session.commit()
    await db_session.refresh(model)
    return model


async def test_get_model_guided_view(client, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/models/{completed_model_with_leaderboard.id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ready"
    assert body["active_candidate"]["algorithm"] == "flaml_lgbm"
    assert body["active_candidate"]["role"] == "recommended"
    assert body["latest_run"]["status"] == "completed"
    assert body["latest_run"]["interpretation_summary"] == "A plain-English summary."


async def test_get_model_leaderboard_recommended_first(client, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/models/{completed_model_with_leaderboard.id}/leaderboard")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ready"
    assert len(body["candidates"]) == 4
    assert body["candidates"][0]["role"] == "recommended"
    assert body["candidates"][0]["algorithm"] == "flaml_lgbm"
    remaining_roles = [c["role"] for c in body["candidates"][1:]]
    assert remaining_roles == ["baseline", "baseline", "baseline"]
    assert body["run"]["row_count_used"] == 6


async def test_get_model_for_spec_delegates_to_guided_view(client, confirmed_spec, completed_model_with_leaderboard):
    resp = await client.get(f"/api/v1/modeling-specs/{confirmed_spec.id}/models")
    assert resp.status_code == 200
    assert resp.json()["id"] == completed_model_with_leaderboard.id


async def test_list_models_empty(client):
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_models_returns_shape_and_ordering(client, confirmed_spec, completed_model_with_leaderboard):
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1

    item = items[0]
    assert item["id"] == completed_model_with_leaderboard.id
    assert item["dataset_name"] == "types_sample.csv"
    assert item["status"] == "ready"
    assert item["algorithm"] == "flaml_lgbm"
    assert item["primary_metric_label"] == "AUC"
    assert item["primary_metric_value"] == 0.8


async def test_list_models_reflects_retrain_in_progress(client, confirmed_spec, completed_model_with_leaderboard):
    # Retraining reuses the spec's existing model slot; active_candidate_id
    # (and therefore the list's algorithm/metric) stays pointed at the
    # previous run's winner until the new run completes.
    build_resp = await client.post(f"/api/v1/modeling-specs/{confirmed_spec.id}/build")
    assert build_resp.status_code == 202

    resp = await client.get("/api/v1/models")
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == completed_model_with_leaderboard.id
    assert items[0]["status"] == "training"
    assert items[0]["algorithm"] == "flaml_lgbm"  # stale-but-valid, unchanged until the new run completes
