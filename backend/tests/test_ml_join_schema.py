import pytest_asyncio

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.modeling_spec import ModelingSpec
from app.models.modeling_spec_join_dataset import ModelingSpecJoinDataset
from app.services.dataset_profiles import get_latest_profile
from app.services.ml.join_schema import resolve_spec_columns


async def _make_dataset(db_session, default_org_id, *, name, content_hash, columns) -> Dataset:
    dataset = Dataset(
        organization_id=default_org_id,
        name=name,
        storage_path=f"{default_org_id}/{name}",
        content_hash=content_hash,
        row_count=10,
        column_count=len(columns),
        status="profiled",
    )
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(
        DatasetProfile(
            organization_id=default_org_id,
            dataset_id=dataset.id,
            content_hash=content_hash,
            row_count=10,
            column_count=len(columns),
            columns=columns,
        )
    )
    await db_session.commit()
    await db_session.refresh(dataset)
    return dataset


@pytest_asyncio.fixture
async def base_dataset(db_session, default_org_id) -> Dataset:
    return await _make_dataset(
        db_session, default_org_id,
        name="base.csv", content_hash="basehash",
        columns=[
            {"name": "fips", "dtype": "id"},
            {"name": "amount", "dtype": "numeric"},
        ],
    )


async def test_resolve_spec_columns_no_joins_returns_base_only(db_session, default_org_id, base_dataset):
    spec = ModelingSpec(organization_id=default_org_id, dataset_id=base_dataset.id, status="draft")
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)

    profile = await get_latest_profile(db_session, base_dataset)
    result = await resolve_spec_columns(db_session, spec, base_dataset, profile)

    assert {c["name"]: c["source"] for c in result} == {"fips": "base.csv", "amount": "base.csv"}
    assert all(c["usable"] for c in result)


async def test_resolve_spec_columns_includes_joined_dataset_columns(db_session, default_org_id, base_dataset):
    joined = await _make_dataset(
        db_session, default_org_id,
        name="region_stats.csv", content_hash="joinhash",
        columns=[
            {"name": "fips", "dtype": "id"},
            {"name": "population", "dtype": "numeric"},
        ],
    )
    spec = ModelingSpec(organization_id=default_org_id, dataset_id=base_dataset.id, status="draft")
    db_session.add(spec)
    await db_session.flush()
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=joined.id,
            join_key_column="fips",
            join_type="left",
        )
    )
    await db_session.commit()
    await db_session.refresh(spec)

    profile = await get_latest_profile(db_session, base_dataset)
    result = await resolve_spec_columns(db_session, spec, base_dataset, profile)

    by_name = {c["name"]: c for c in result}
    assert by_name["population"]["source"] == "region_stats.csv"
    assert by_name["population"]["usable"] is True
    assert by_name["amount"]["source"] == "base.csv"
    # The join key is deduplicated into a single entry, not listed once per side.
    assert list(r["name"] for r in result).count("fips") == 1
    assert by_name["fips"]["source"] == "shared join key"
    assert by_name["fips"]["usable"] is True


async def test_resolve_spec_columns_flags_ambiguous_collision(db_session, default_org_id, base_dataset):
    # Both the base dataset and the joined dataset have a non-key "amount" column.
    joined = await _make_dataset(
        db_session, default_org_id,
        name="colliding.csv", content_hash="collidehash",
        columns=[
            {"name": "fips", "dtype": "id"},
            {"name": "amount", "dtype": "numeric"},
        ],
    )
    spec = ModelingSpec(organization_id=default_org_id, dataset_id=base_dataset.id, status="draft")
    db_session.add(spec)
    await db_session.flush()
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=joined.id,
            join_key_column="fips",
            join_type="left",
        )
    )
    await db_session.commit()
    await db_session.refresh(spec)

    profile = await get_latest_profile(db_session, base_dataset)
    result = await resolve_spec_columns(db_session, spec, base_dataset, profile)

    amount_entries = [c for c in result if c["name"] == "amount"]
    assert len(amount_entries) == 2  # both sides still listed, just marked unusable
    assert all(c["usable"] is False for c in amount_entries)


async def test_resolve_spec_columns_skips_unprofiled_joined_dataset(db_session, default_org_id, base_dataset):
    unprofiled = Dataset(
        organization_id=default_org_id,
        name="still_profiling.csv",
        storage_path=f"{default_org_id}/still_profiling.csv",
        content_hash="unprofiledhash",
        status="profiling",
    )
    db_session.add(unprofiled)
    await db_session.flush()

    spec = ModelingSpec(organization_id=default_org_id, dataset_id=base_dataset.id, status="draft")
    db_session.add(spec)
    await db_session.flush()
    db_session.add(
        ModelingSpecJoinDataset(
            organization_id=default_org_id,
            modeling_spec_id=spec.id,
            dataset_id=unprofiled.id,
            join_key_column="fips",
            join_type="left",
        )
    )
    await db_session.commit()
    await db_session.refresh(spec)

    profile = await get_latest_profile(db_session, base_dataset)
    result = await resolve_spec_columns(db_session, spec, base_dataset, profile)

    assert {c["name"] for c in result} == {"fips", "amount"}  # unprofiled join silently absent
