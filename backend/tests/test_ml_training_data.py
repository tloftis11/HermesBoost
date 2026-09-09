import pytest_asyncio

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.modeling_spec import ModelingSpec
from app.models.modeling_spec_join_dataset import ModelingSpecJoinDataset
from app.services.ml.training_data import TrainingDataError, build_training_dataframe
from app.services.storage import LocalStorageBackend, set_storage_backend_for_tests


@pytest_asyncio.fixture
async def storage(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    set_storage_backend_for_tests(backend)
    return backend


@pytest_asyncio.fixture
async def base_dataset(db_session, default_org_id, storage, fixtures_dir):
    data = (fixtures_dir / "training_join_base.csv").read_bytes()
    storage.upload("datasets", f"{default_org_id}/base.csv", data)

    dataset = Dataset(
        organization_id=default_org_id,
        name="training_join_base.csv",
        storage_path=f"{default_org_id}/base.csv",
        content_hash="basehash",
        row_count=40,
        column_count=3,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="basehash",
            row_count=40,
            column_count=3,
            columns=[
                {"name": "site_key", "dtype": "id", "null_rate": 0.0},
                {"name": "feature_a", "dtype": "numeric", "null_rate": 0.0},
                {"name": "target_value", "dtype": "numeric", "null_rate": 0.0},
            ],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


@pytest_asyncio.fixture
async def joined_dataset(db_session, default_org_id, storage, fixtures_dir):
    data = (fixtures_dir / "training_join_extra.csv").read_bytes()
    storage.upload("datasets", f"{default_org_id}/extra.csv", data)

    dataset = Dataset(
        organization_id=default_org_id,
        name="training_join_extra.csv",
        storage_path=f"{default_org_id}/extra.csv",
        content_hash="extrahash",
        row_count=34,
        column_count=2,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="extrahash",
            row_count=34,
            column_count=2,
            columns=[
                {"name": "site_key", "dtype": "id", "null_rate": 0.0},
                {"name": "feature_b", "dtype": "numeric", "null_rate": 0.0},
            ],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


async def _make_spec(db_session, default_org_id, dataset, target, candidate_features):
    spec = ModelingSpec(
        organization_id=default_org_id,
        dataset_id=dataset.id,
        status="confirmed",
        task_type="classification",
        target=target,
        candidate_features=candidate_features,
    )
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


async def test_build_training_dataframe_no_join(db_session, default_org_id, base_dataset):
    spec = await _make_spec(db_session, default_org_id, base_dataset, "target_value", ["feature_a"])

    result = await build_training_dataframe(db_session, spec)

    assert result.row_count == 40
    assert result.feature_dtypes == {"feature_a": "numeric"}
    assert result.warnings == []


async def test_build_training_dataframe_left_join_warns_on_new_nulls(
    db_session, default_org_id, base_dataset, joined_dataset
):
    spec = await _make_spec(
        db_session, default_org_id, base_dataset, "target_value", ["feature_a", "feature_b"]
    )
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=joined_dataset.id,
            join_key_column="site_key",
            join_type="left",
        )
    )
    await db_session.commit()

    result = await build_training_dataframe(db_session, spec)

    assert result.row_count == 40  # left join keeps every base row
    assert result.feature_dtypes == {"feature_a": "numeric", "feature_b": "numeric"}
    assert any("feature_b" in w and "null" in w for w in result.warnings)


async def test_build_training_dataframe_inner_join_warns_on_row_loss(
    db_session, default_org_id, base_dataset, joined_dataset
):
    spec = await _make_spec(
        db_session, default_org_id, base_dataset, "target_value", ["feature_a", "feature_b"]
    )
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=joined_dataset.id,
            join_key_column="site_key",
            join_type="inner",
        )
    )
    await db_session.commit()

    result = await build_training_dataframe(db_session, spec)

    assert result.row_count == 34  # only the 34 matching keys survive an inner join
    assert any("inner join dropped" in w for w in result.warnings)


async def test_build_training_dataframe_rejects_unknown_join_key(
    db_session, default_org_id, base_dataset, joined_dataset
):
    spec = await _make_spec(db_session, default_org_id, base_dataset, "target_value", ["feature_a"])
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=joined_dataset.id,
            join_key_column="not_a_real_column",
            join_type="left",
        )
    )
    await db_session.commit()

    try:
        await build_training_dataframe(db_session, spec)
        assert False, "expected TrainingDataError"
    except TrainingDataError as exc:
        assert "not_a_real_column" in str(exc)


async def test_build_training_dataframe_rejects_ambiguous_column_collision(
    db_session, default_org_id, base_dataset, storage, fixtures_dir
):
    # A second joined dataset that (ambiguously) also has a "feature_a" column
    data = (fixtures_dir / "training_join_extra.csv").read_bytes()
    storage.upload("datasets", f"{default_org_id}/collide.csv", data)
    colliding = Dataset(
        organization_id=default_org_id,
        name="colliding.csv",
        storage_path=f"{default_org_id}/collide.csv",
        content_hash="collidehash",
        row_count=34,
        column_count=2,
        status="profiled",
    )
    db_session.add(colliding)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=colliding.id,
            content_hash="collidehash",
            row_count=34,
            column_count=2,
            columns=[
                {"name": "site_key", "dtype": "id", "null_rate": 0.0},
                # collides with the base dataset's own "feature_a" column name
                {"name": "feature_a", "dtype": "numeric", "null_rate": 0.0},
            ],
        )
    )
    await db_session.commit()

    spec = await _make_spec(db_session, default_org_id, base_dataset, "target_value", ["feature_a"])
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=colliding.id,
            join_key_column="site_key",
            join_type="left",
        )
    )
    await db_session.commit()

    try:
        await build_training_dataframe(db_session, spec)
        assert False, "expected TrainingDataError"
    except TrainingDataError as exc:
        assert "feature_a" in str(exc)


async def test_build_training_dataframe_rejects_when_feature_mostly_null(
    db_session, default_org_id, storage
):
    # Hand-built CSV: target is fine, but "sparse" is >90% null.
    csv_bytes = b"row_id,sparse,target\n" + b"".join(
        f"{i},{'' if i > 2 else 1.0},{i % 2}\n".encode() for i in range(1, 26)
    )
    storage.upload("datasets", f"{default_org_id}/sparse.csv", csv_bytes)
    dataset = Dataset(
        organization_id=default_org_id,
        name="sparse.csv",
        storage_path=f"{default_org_id}/sparse.csv",
        content_hash="sparsehash",
        row_count=25,
        column_count=3,
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash="sparsehash",
            row_count=25,
            column_count=3,
            columns=[
                {"name": "row_id", "dtype": "id", "null_rate": 0.0},
                {"name": "sparse", "dtype": "numeric", "null_rate": 0.92},
                {"name": "target", "dtype": "numeric", "null_rate": 0.0},
            ],
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)

    spec = await _make_spec(db_session, default_org_id, dataset, "target", ["sparse"])

    try:
        await build_training_dataframe(db_session, spec)
        assert False, "expected TrainingDataError"
    except TrainingDataError as exc:
        assert "sparse" in str(exc)
