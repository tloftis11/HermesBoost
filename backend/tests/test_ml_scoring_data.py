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
    dedupe_to_latest_period,
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


def test_resolve_entity_id_column_override_bypasses_uniqueness_guess():
    # "fips" repeats across a panel and so is profiled as plain "numeric",
    # not "id" -- an explicit override should still resolve it directly.
    columns = [
        {"name": "fips", "dtype": "numeric"},
        {"name": "year", "dtype": "numeric"},
    ]
    assert _resolve_entity_id_column(columns, override="fips") == "fips"


def test_resolve_entity_id_column_override_not_in_columns_returns_none():
    columns = [{"name": "fips", "dtype": "numeric"}]
    assert _resolve_entity_id_column(columns, override="not_a_real_column") is None


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


def _panel_csv() -> bytes:
    # Two entities ("A", "B"), each appearing twice (like two years of a
    # panel) -- "entity" is not row-unique, so it would never be profiled
    # as dtype "id" on its own.
    lines = [
        "entity,year,feature_a",
        "A,2023,1.0",
        "B,2023,2.0",
        "A,2024,3.0",
        "B,2024,4.0",
    ]
    return ("\n".join(lines) + "\n").encode()


async def _make_panel_dataset(db_session, default_org_id, storage) -> Dataset:
    csv_bytes = _panel_csv()
    storage.upload("datasets", f"{default_org_id}/panel.csv", csv_bytes)
    dataset = Dataset(
        organization_id=default_org_id,
        name="panel.csv",
        storage_path=f"{default_org_id}/panel.csv",
        content_hash="panelhash",
        row_count=4,
        column_count=3,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="panelhash",
            row_count=4,
            column_count=3,
            columns=[
                {"name": "entity", "dtype": "categorical", "null_rate": 0.0},
                {"name": "year", "dtype": "numeric", "null_rate": 0.0},
                {"name": "feature_a", "dtype": "numeric", "null_rate": 0.0},
            ],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


async def test_build_scoring_dataframe_honors_entity_id_column_override_on_panel_data(
    db_session, default_org_id, storage
):
    dataset = await _make_panel_dataset(db_session, default_org_id, storage)
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="regression",
        target="feature_a",
        candidate_features=["year"],
        entity_id_column="entity",
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    result = await build_scoring_dataframe(db_session, spec)

    assert result.entity_ids == ["A", "B", "A", "B"]  # repeats, not a positional index


async def test_build_scoring_dataframe_rejects_bad_entity_id_column(db_session, default_org_id, storage):
    dataset = await _make_panel_dataset(db_session, default_org_id, storage)
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="regression",
        target="feature_a",
        candidate_features=["year"],
        entity_id_column="not_a_real_column",
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    try:
        await build_scoring_dataframe(db_session, spec)
        assert False, "expected ScoringDataError"
    except ScoringDataError as exc:
        assert "not_a_real_column" in str(exc)


async def test_dedupe_to_latest_period_keeps_latest_year_per_entity(db_session, default_org_id, storage):
    dataset = await _make_panel_dataset(db_session, default_org_id, storage)
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="regression",
        target="feature_a",
        candidate_features=["year", "feature_a"],
        entity_id_column="entity",
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    result = await build_scoring_dataframe(db_session, spec)
    assert result.entity_ids == ["A", "B", "A", "B"]  # both years scored, pre-dedupe

    deduped = dedupe_to_latest_period(result, spec.candidate_features)

    assert deduped.entity_ids == ["A", "B"]  # one row per entity, order preserved
    assert deduped.row_count == 2
    assert list(deduped.dataframe["year"]) == [2024, 2024]  # the later year won for both
    assert list(deduped.dataframe["feature_a"]) == [3.0, 4.0]  # the 2024 rows' own values


async def test_dedupe_to_latest_period_noop_when_no_duplicate_entities(db_session, default_org_id, storage):
    dataset = await _make_dataset(
        db_session, default_org_id, storage,
        name="base.csv", content_hash="nodupe", csv_bytes=_csv(5),
    )
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target="feature_a",
        candidate_features=["feature_a"],
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    result = await build_scoring_dataframe(db_session, spec)
    deduped = dedupe_to_latest_period(result, spec.candidate_features)

    assert deduped is result  # already one row per entity -- passed through untouched


async def test_dedupe_to_latest_period_noop_when_no_time_column_detected(db_session, default_org_id, storage):
    dataset = await _make_panel_dataset(db_session, default_org_id, storage)
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="regression",
        target="feature_a",
        candidate_features=["feature_a"],  # "year" not selected -- no detectable period column
        entity_id_column="entity",
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    result = await build_scoring_dataframe(db_session, spec)
    deduped = dedupe_to_latest_period(result, spec.candidate_features)

    assert deduped.entity_ids == ["A", "B", "A", "B"]  # unchanged -- can't tell which row is "latest"


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
