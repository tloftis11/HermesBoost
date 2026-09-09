import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.tasks.score_model as score_model_task
import app.tasks.train_model as train_model_task
from app.config import settings
from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.model import Model
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.models.scheduled_score import ScheduledScore
from app.services.profiling import profile_csv_bytes
from app.services.storage import LocalStorageBackend, set_storage_backend_for_tests
from app.tasks.score_model import _score_model_async
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
    monkeypatch.setattr(score_model_task, "async_session_maker", test_session_maker)


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
async def ready_model(db_session, default_org_id, classification_spec, monkeypatch):
    """A model that has already been trained (real FLAML fit) and is ready
    to score against -- the scoring tests' actual subject under test."""
    monkeypatch.setattr(settings, "FLAML_TIME_BUDGET_SECONDS", 3)

    model = Model(organization_id=default_org_id, modeling_spec_id=classification_spec.id, status="training")
    db_session.add(model)
    await db_session.flush()
    train_run = ModelRun(organization_id=default_org_id, model_id=model.id, run_type="train", status="running")
    db_session.add(train_run)
    await db_session.commit()
    await db_session.refresh(train_run)

    await _train_model_async(train_run.id)

    await db_session.refresh(model)
    assert model.status == "ready"  # sanity check the fixture itself trained successfully
    return model


@pytest_asyncio.fixture
async def score_run(db_session, default_org_id, ready_model):
    run = ModelRun(organization_id=default_org_id, model_id=ready_model.id, run_type="score", status="running")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _get_scores(db_session, model_run_id: str) -> list[ScheduledScore]:
    result = await db_session.execute(
        select(ScheduledScore).where(ScheduledScore.model_run_id == model_run_id)
    )
    return list(result.scalars().all())


async def test_score_model_completes_run_and_writes_rows(db_session, score_run):
    await _score_model_async(score_run.id)

    await db_session.refresh(score_run)
    assert score_run.status == "completed"
    assert score_run.row_count_used == 90
    assert score_run.completed_at is not None

    rows = await _get_scores(db_session, score_run.id)
    assert len(rows) == 90


async def test_score_model_writes_classification_label_and_probability(db_session, score_run, ready_model):
    await _score_model_async(score_run.id)

    rows = await _get_scores(db_session, score_run.id)
    for row in rows:
        assert row.predicted_label in ("0", "1")
        assert 0.0 <= row.predicted_probability <= 1.0
        assert row.predicted_value is None  # classification -- regression-only field stays null
        assert row.model_id == ready_model.id
        assert row.model_candidate_id == ready_model.active_candidate_id


async def test_score_model_entity_id_falls_back_to_positional_index(db_session, score_run):
    # training_sample.csv's "row_id" column is sequential 1..90 (all
    # distinct) -- profiled as dtype "id", so it should resolve as the
    # entity_id source rather than falling back to a raw index.
    await _score_model_async(score_run.id)

    rows = await _get_scores(db_session, score_run.id)
    entity_ids = sorted(int(r.entity_id) for r in rows)
    assert entity_ids == list(range(1, 91))


async def test_score_model_does_not_error_the_model_on_failure(db_session, ready_model, default_org_id):
    # A score run against a model whose active candidate id is bogus
    # (simulating a corrupted/missing artifact reference) should fail the
    # *run*, not flip the model itself to "error" -- it's still ready.
    ready_model.active_candidate_id = "00000000-0000-0000-0000-000000000000"
    await db_session.commit()

    run = ModelRun(organization_id=default_org_id, model_id=ready_model.id, run_type="score", status="running")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    await _score_model_async(run.id)

    await db_session.refresh(run)
    assert run.status == "error"
    assert run.error_message

    await db_session.refresh(ready_model)
    assert ready_model.status == "ready"  # unchanged -- only the score run failed
