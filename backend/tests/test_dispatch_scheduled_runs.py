from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

import scripts.dispatch_scheduled_runs as dispatcher
from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.model import Model
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec


@pytest_asyncio.fixture(autouse=True)
async def _bind_dispatcher_to_test_engine(test_engine, monkeypatch):
    test_session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(dispatcher, "async_session_maker", test_session_maker)


@pytest_asyncio.fixture
def enqueued(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(dispatcher.train_model, "delay", lambda run_id: calls.append(("train", run_id)))
    monkeypatch.setattr(dispatcher.score_model, "delay", lambda run_id: calls.append(("score", run_id)))
    return calls


@pytest_asyncio.fixture
async def confirmed_spec(db_session, default_org_id):
    dataset = Dataset(
        organization_id=default_org_id,
        name="d.csv",
        storage_path=f"{default_org_id}/d.csv",
        content_hash="h",
        row_count=10,
        column_count=2,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="h",
            row_count=10,
            column_count=2,
            columns=[{"name": "a", "dtype": "numeric"}, {"name": "b", "dtype": "numeric"}],
        )
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="a",
        candidate_features=["b"],
        retrain_cadence="weekly",
        score_cadence="daily",
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


async def _make_model_with_run(db_session, default_org_id, spec, *, model_status, run_type, started_at, run_status="completed"):
    model = Model(organization_id=default_org_id, modeling_spec_id=spec.id, status=model_status)
    db_session.add(model)
    await db_session.flush()
    run = ModelRun(
        organization_id=default_org_id, model_id=model.id, run_type=run_type,
        status=run_status, started_at=started_at, completed_at=started_at,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(model)
    return model


async def test_dispatch_skips_spec_with_no_model(db_session, confirmed_spec, enqueued):
    await dispatcher.main()
    assert enqueued == []


async def test_dispatch_enqueues_train_when_overdue(db_session, default_org_id, confirmed_spec, enqueued):
    old = datetime.now(timezone.utc) - timedelta(days=8)  # weekly cadence, 8 days ago
    await _make_model_with_run(
        db_session, default_org_id, confirmed_spec, model_status="ready", run_type="train", started_at=old
    )
    await dispatcher.main()
    assert any(kind == "train" for kind, _ in enqueued)


async def test_dispatch_skips_train_when_not_due(db_session, default_org_id, confirmed_spec, enqueued):
    recent = datetime.now(timezone.utc) - timedelta(hours=1)  # weekly cadence, 1 hour ago
    await _make_model_with_run(
        db_session, default_org_id, confirmed_spec, model_status="ready", run_type="train", started_at=recent
    )
    await dispatcher.main()
    assert not any(kind == "train" for kind, _ in enqueued)


async def test_dispatch_skips_when_last_run_still_running(db_session, default_org_id, confirmed_spec, enqueued):
    old = datetime.now(timezone.utc) - timedelta(days=8)
    await _make_model_with_run(
        db_session, default_org_id, confirmed_spec, model_status="training",
        run_type="train", started_at=old, run_status="running",
    )
    await dispatcher.main()
    assert not any(kind == "train" for kind, _ in enqueued)


async def test_dispatch_scores_immediately_on_first_ever_score_run(db_session, default_org_id, confirmed_spec, enqueued):
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)  # train just happened, not due for retrain
    await _make_model_with_run(
        db_session, default_org_id, confirmed_spec, model_status="ready", run_type="train", started_at=recent
    )
    await dispatcher.main()
    assert any(kind == "score" for kind, _ in enqueued)
    assert not any(kind == "train" for kind, _ in enqueued)


async def test_dispatch_skips_score_when_model_not_ready(db_session, default_org_id, confirmed_spec, enqueued):
    old = datetime.now(timezone.utc) - timedelta(days=8)
    await _make_model_with_run(
        db_session, default_org_id, confirmed_spec, model_status="training", run_type="train", started_at=old
    )
    await dispatcher.main()
    assert any(kind == "train" for kind, _ in enqueued)  # retrain still fires -- overdue regardless of status
    assert not any(kind == "score" for kind, _ in enqueued)  # score never checked since model isn't ready
