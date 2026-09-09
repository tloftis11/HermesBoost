"""Profile-only view of a modeling spec's base + attached join datasets'
columns -- for callers that need to know what columns *exist* without
materializing any actual data (e.g. the intent chat, which only ever sees
profiling statistics). Mirrors the ownership/collision rules in
training_data._materialize_join_columns (which does the real, data-touching
version for training/scoring) so what a caller offers as available columns
matches what will actually build.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.modeling_spec import ModelingSpec
from app.models.modeling_spec_join_dataset import ModelingSpecJoinDataset
from app.services.dataset_profiles import get_latest_profile


async def resolve_spec_columns(
    db: AsyncSession,
    spec: ModelingSpec,
    base_dataset: Dataset,
    base_profile: DatasetProfile,
) -> list[dict]:
    """One entry per column across the base dataset and any attached join
    datasets: {"name", "dtype", "source", "usable"}.

    `source` is the owning dataset's name, or "shared join key" for a join
    key column (present on both sides by definition, so it's deduplicated
    into a single entry rather than listed once per dataset). `usable` is
    False for a non-key column name that appears in more than one attached
    dataset -- candidate_features aren't qualified by source dataset, so a
    colliding name can never actually be selected (see
    _materialize_join_columns's collision check, which this mirrors).
    Datasets/profiles that no longer exist or haven't finished profiling
    are silently skipped, matching how build_scoring_dataframe/
    build_training_dataframe would simply not see them either.
    """
    join_rows = (
        await db.execute(
            select(ModelingSpecJoinDataset).where(ModelingSpecJoinDataset.modeling_spec_id == spec.id)
        )
    ).scalars().all()

    sources: list[tuple[str, list[dict]]] = [(base_dataset.name, base_profile.columns)]
    join_keys: set[str] = set()
    for jr in join_rows:
        joined_dataset = await db.get(Dataset, jr.dataset_id)
        if joined_dataset is None:
            continue
        joined_profile = await get_latest_profile(db, joined_dataset)
        if joined_profile is None:
            continue
        sources.append((joined_dataset.name, joined_profile.columns))
        join_keys.add(jr.join_key_column)

    # Count how many sources contribute each non-key column name -- a name
    # appearing more than once (excluding join keys, which legitimately
    # exist on both sides) is ambiguous.
    name_counts: dict[str, int] = {}
    for _, cols in sources:
        seen_in_this_source: set[str] = set()
        for c in cols:
            name = c["name"]
            if name in join_keys or name in seen_in_this_source:
                continue
            seen_in_this_source.add(name)
            name_counts[name] = name_counts.get(name, 0) + 1

    out: list[dict] = []
    emitted_join_keys: set[str] = set()
    for source_name, cols in sources:
        for c in cols:
            name = c["name"]
            if name in join_keys:
                if name in emitted_join_keys:
                    continue  # already emitted once, from whichever source hit it first
                emitted_join_keys.add(name)
                out.append({"name": name, "dtype": c["dtype"], "source": "shared join key", "usable": True})
                continue
            out.append({
                "name": name,
                "dtype": c["dtype"],
                "source": source_name,
                "usable": name_counts.get(name, 0) <= 1,
            })
    return out
