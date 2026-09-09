from datetime import date, timedelta

import pytest_asyncio

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.dataset_series import DatasetSeries
from app.models.modeling_spec import ModelingSpec
from app.services.ml.scoring_data import (
    ScoringDataError,
    _resolve_entity_id_column,
    _resolve_latest_in_series,
    build_scoring_dataframe,
)
from app.services.storage import LocalStorageBackend, set_storage_backend_for_tests


def test_resolve_entity_id_column_single_id_column():
    columns = [
        {"name": "row_id", "dtype": "id"},
        {"name": "amount", "dtype": "numeric"},
        {"name": "category", "dtype": "categorical"},
    ]
    assert _resolve_entity_id_column(columns) == "row_id"


def test_resolve_entity_id_column_none_falls_back_to_none():
    columns = [{"name": "amount", "dtype": "numeric"}, {"name": "category", "dtype": "categorical"}]
    assert _resolve_entity_id_column(columns) is None


def test_resolve_entity_id_column_multiple_falls_back_to_none():
    columns = [{"name": "row_id", "dtype": "id"}, {"name": "other_id", "dtype": "id"}]
    assert _resolve_entity_id_column(columns) is None


@pytest_asyncio.fixture
async def storage(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    set_storage_backend_for_tests(backend)
    return backend


async def _make_dataset(db_session, default_org_id, storage, *, name, content_hash, csv_bytes, series_id=None, as_of_date=None):
    storage.upload("datasets", f"{default_org_id}/{name}", csv_bytes)
    dataset = Dataset(
        organization_id=default_org_id,
        name=name,
        storage_path=f"{default_org_id}/{name}",
        content_hash=content_hash,
        row_count=csv_bytes.count(b"\n") - 1,
        column_count=2,
        status="profiled",
        series_id=series_id,
        as_of_date=as_of_date,
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash=content_hash,
            row_count=dataset.row_count,
            column_count=2,
            columns=[
                {"name": "row_id", "dtype": "id", "null_rate": 0.0},
                {"name": "feature_a", "dtype": "numeric", "null_rate": 0.0},
            ],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


@pytest_asyncio.fixture
async def series(db_session, default_org_id):
    s = DatasetSeries(organization_id=default_org_id, name="daily_counts")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _csv(n: int) -> bytes:
    lines = ["row_id,feature_a"] + [f"{i},{i * 1.5}" for i in range(1, n + 1)]
    return ("\n".join(lines) + "\n").encode()


async def test_resolve_latest_in_series_picks_most_recent_by_as_of_date(db_session, default_org_id, storage, series):
    today = date.today()
    await _make_dataset(
        db_session, default_org_id, storage,
        name="old.csv", content_hash="h1", csv_bytes=_csv(5),
        series_id=series.id, as_of_date=today - timedelta(days=2),
    )
    newest = await _make_dataset(
        db_session, default_org_id, storage,
        name="new.csv", content_hash="h2", csv_bytes=_csv(8),
        series_id=series.id, as_of_date=today,
    )

    resolved = await _resolve_latest_in_series(db_session, series.id, default_org_id)
    assert resolved.id == newest.id


async def test_resolve_latest_in_series_raises_when_none_profiled(db_session, default_org_id, series):
    try:
        await _resolve_latest_in_series(db_session, series.id, default_org_id)
        assert False, "expected ScoringDataError"
    except ScoringDataError:
        pass


async def test_build_scoring_dataframe_basic(db_session, default_org_id, storage):
    dataset = await _make_dataset(
        db_session, default_org_id, storage,
        name="base.csv", content_hash="basehash", csv_bytes=_csv(10),
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="feature_a",  # unused by scoring, but required by the column model
        candidate_features=["feature_a"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    result = await build_scoring_dataframe(db_session, spec)

    assert result.row_count == 10
    assert result.resolved_dataset_id == dataset.id
    assert result.entity_ids == [str(i) for i in range(1, 11)]
    assert list(result.dataframe.columns) >= ["feature_a"]


async def test_build_scoring_dataframe_resolves_series(db_session, default_org_id, storage, series):
    today = date.today()
    base = await _make_dataset(
        db_session, default_org_id, storage,
        name="base.csv", content_hash="baseh", csv_bytes=_csv(5),
        series_id=series.id, as_of_date=today - timedelta(days=1),
    )
    newer = await _make_dataset(
        db_session, default_org_id, storage,
        name="newer.csv", content_hash="newh", csv_bytes=_csv(7),
        series_id=series.id, as_of_date=today,
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=base.id,  # the spec's literal base dataset is the OLDER one
        status="confirmed",
        task_type="classification",
        target="feature_a",
        candidate_features=["feature_a"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    result = await build_scoring_dataframe(db_session, spec)

    assert result.resolved_dataset_id == newer.id  # resolved to the newer dataset in the series
    assert result.row_count == 7
    assert result.score_date == today


async def test_build_scoring_dataframe_rejects_missing_column(db_session, default_org_id, storage):
    dataset = await _make_dataset(
        db_session, default_org_id, storage,
        name="base.csv", content_hash="basehash2", csv_bytes=_csv(10),
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="feature_a",
        candidate_features=["not_a_real_column"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    try:
        await build_scoring_dataframe(db_session, spec)
        assert False, "expected ScoringDataError"
    except ScoringDataError as exc:
        assert "not_a_real_column" in str(exc)
