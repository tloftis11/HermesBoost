import pandas as pd
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.tasks.train_model as train_model_task
from app.config import settings
from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.model import Model
from app.models.model_candidate import ModelCandidate
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.services.ml.persistence import load_model_artifact
from app.services.profiling import profile_csv_bytes
from app.services.storage import LocalStorageBackend, set_storage_backend_for_tests
from app.tasks.train_model import _train_model_async


@pytest_asyncio.fixture
async def storage(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    set_storage_backend_for_tests(backend)
    return backend


@pytest_asyncio.fixture(autouse=True)
async def _bind_task_to_test_engine(test_engine, monkeypatch):
    # _train_model_async opens its own session via the module-level
    # async_session_maker it imported from app.db -- that name is bound at
    # import time and points at the real DATABASE_URL, not this test's
    # in-memory engine. Rebind the task module's reference so it shares the
    # same StaticPool connection (and therefore sees) as db_session.
    test_session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(train_model_task, "async_session_maker", test_session_maker)


@pytest_asyncio.fixture
async def classification_spec(db_session, default_org_id, storage, fixtures_dir):
    data = (fixtures_dir / "training_sample.csv").read_bytes()
    storage.upload("datasets", f"{default_org_id}/training_sample.csv", data)
    profile_dict = profile_csv_bytes(data)

    dataset = Dataset(
        organization_id=default_org_id,
        name="training_sample.csv",
        storage_path=f"{default_org_id}/training_sample.csv",
        content_hash="trainhash",
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
            content_hash="trainhash",
            row_count=profile_dict["row_count"],
            column_count=profile_dict["column_count"],
            columns=profile_dict["columns"],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)

    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="label",
        candidate_features=["num_a", "num_b", "cat_c"],
        evaluation_metric="auc",
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


@pytest_asyncio.fixture
async def model_run(db_session, default_org_id, classification_spec):
    model = Model(organization_id=default_org_id, modeling_spec_id=classification_spec.id, status="training")
    db_session.add(model)
    await db_session.flush()

    run = ModelRun(organization_id=default_org_id, model_id=model.id, run_type="train", status="running")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _get_candidates(db_session, model_run_id: str) -> list[ModelCandidate]:
    result = await db_session.execute(
        select(ModelCandidate).where(ModelCandidate.model_run_id == model_run_id)
    )
    return list(result.scalars().all())


async def test_train_model_completes_run_with_interpretation(db_session, model_run, monkeypatch):
    monkeypatch.setattr(settings, "FLAML_TIME_BUDGET_SECONDS", 3)

    await _train_model_async(model_run.id)

    await db_session.refresh(model_run)
    assert model_run.status == "completed"
    assert model_run.ml_task == "classification"
    assert model_run.row_count_used == 90
    assert model_run.completed_at is not None
    assert "Fake interpretation" in model_run.interpretation_summary
    assert model_run.interpretation_key_drivers == [
        {
            "feature": "placeholder_feature",
            "plain_description": "Fake driver for offline testing.",
            "relative_importance": 1.0,
        }
    ]
    assert model_run.interpretation_model == "fake-model"


async def test_train_model_creates_four_candidates_with_metrics(db_session, model_run, monkeypatch):
    monkeypatch.setattr(settings, "FLAML_TIME_BUDGET_SECONDS", 3)

    await _train_model_async(model_run.id)

    candidates = await _get_candidates(db_session, model_run.id)

    assert len(candidates) == 4
    roles = [c.role for c in candidates]
    assert roles.count("recommended") == 1
    assert roles.count("baseline") == 3

    algorithms = {c.algorithm for c in candidates}
    assert {"logistic_regression", "random_forest", "xgboost"} <= algorithms
    assert any(a.startswith("flaml_") for a in algorithms)

    for c in candidates:
        assert c.ml_task == "classification"
        assert c.target_column == "label"
        assert set(c.feature_columns) == {"num_a", "num_b", "cat_c"}
        assert c.label_classes == ["0", "1"]
        assert 0.0 <= c.metrics["auc"] <= 1.0
        assert "calibration_error" in c.metrics
        assert c.feature_importance
        assert c.train_time_seconds is not None
        assert c.storage_bucket == "models"
        assert c.storage_path


async def test_train_model_candidate_artifacts_round_trip(db_session, model_run, monkeypatch, storage):
    monkeypatch.setattr(settings, "FLAML_TIME_BUDGET_SECONDS", 3)

    await _train_model_async(model_run.id)

    candidates = await _get_candidates(db_session, model_run.id)

    sample = pd.DataFrame({"num_a": [50], "num_b": [0], "cat_c": ["north"]})
    for c in candidates:
        artifact_bytes = storage.download(c.storage_bucket, c.storage_path)
        pipeline = load_model_artifact(artifact_bytes)
        prediction = pipeline.predict(sample)
        assert len(prediction) == 1


async def test_train_model_sets_model_ready_and_active_candidate(db_session, model_run, monkeypatch):
    monkeypatch.setattr(settings, "FLAML_TIME_BUDGET_SECONDS", 3)

    await _train_model_async(model_run.id)

    model = await db_session.get(Model, model_run.model_id)
    await db_session.refresh(model)

    assert model.status == "ready"
    assert model.error_message is None
    assert model.active_candidate_id is not None

    active_candidate = await db_session.get(ModelCandidate, model.active_candidate_id)
    assert active_candidate.role == "recommended"
