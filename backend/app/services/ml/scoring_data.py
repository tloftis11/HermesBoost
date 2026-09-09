"""Builds a clean dataframe to run a fitted candidate's pipeline against --
the scoring-time counterpart to training_data.py. Shares the join
materialization logic (training_data._materialize_join_columns) but has no
target column, no train/test split, and resolves the base dataset through
a recurring series when one is tagged.
"""

from datetime import date

import pandas as pd
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.modeling_spec import ModelingSpec
from app.services.dataset_profiles import get_latest_profile
from app.services.ml.training_data import (
    FEATURE_NULL_REJECT_THRESHOLD,
    FEATURE_NULL_WARN_THRESHOLD,
    TrainingDataError,
    _materialize_join_columns,
)


class ScoringDataError(Exception):
    pass


class ScoringDataResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataframe: pd.DataFrame  # candidate_features + entity_id source column, if resolved
    entity_ids: list[str]  # aligned to dataframe.index
    resolved_dataset_id: str
    score_date: date
    warnings: list[str]
    row_count: int


# Conventionally-named columns treated as a period indicator when
# deduping panel data for scoring -- see dedupe_to_latest_period.
_TIME_COLUMN_NAMES = {"year", "period", "date", "as_of_year", "time", "week", "month"}


def dedupe_to_latest_period(result: ScoringDataResult, candidate_features: list[str]) -> ScoringDataResult:
    """Panel/repeated-observations data -- the same entity_id across
    several historical periods -- is a deliberate, supported shape for
    *training* a rare-event classifier (see _resolve_entity_id_column's
    docstring): a positive example may only exist in a handful of past
    periods, so the training set legitimately repeats each entity once
    per period. But scoring an entity's *current* risk is a different
    question -- returning every historical period as its own row is
    misleading, since a caller has no way to tell which row is "now" and
    an entity can show wildly different scores across its own rows.

    If a conventionally-named period column (year/date/period/etc.) is
    present among the spec's candidate features, keep only each entity's
    most recent row by that column. Entities that only appear once are
    passed through unchanged, and if no period column is detected at all,
    every row is scored as before -- this only ever narrows what's
    already there, never invents a period where none is declared.
    """
    if len(set(result.entity_ids)) == len(result.entity_ids):
        return result  # already one row per entity -- nothing to collapse

    time_col = next((c for c in candidate_features if c.lower() in _TIME_COLUMN_NAMES), None)
    if time_col is None or time_col not in result.dataframe.columns:
        return result  # no detectable period column -- unchanged, as before

    df = result.dataframe.copy()
    df["_entity_id"] = result.entity_ids
    # Unparseable/missing period values sort first (lowest priority) so a
    # row with a real period value always wins the "most recent" slot.
    df["_time"] = pd.to_numeric(df[time_col], errors="coerce").fillna(float("-inf"))
    df["_orig_order"] = range(len(df))

    keep = (
        df.sort_values(["_time", "_orig_order"])
        .groupby("_entity_id", sort=False)
        .tail(1)["_orig_order"]
        .sort_values()
        .tolist()
    )

    return ScoringDataResult(
        dataframe=result.dataframe.iloc[keep].reset_index(drop=True),
        entity_ids=[result.entity_ids[i] for i in keep],
        resolved_dataset_id=result.resolved_dataset_id,
        score_date=result.score_date,
        warnings=result.warnings,
        row_count=len(keep),
    )


async def _resolve_latest_in_series(db: AsyncSession, series_id: str, organization_id: str) -> Dataset:
    result = await db.execute(
        select(Dataset)
        .where(
            Dataset.series_id == series_id,
            Dataset.organization_id == organization_id,
            Dataset.status == "profiled",
        )
        .order_by(Dataset.as_of_date.desc().nulls_last(), Dataset.created_at.desc())
        .limit(1)
    )
    dataset = result.scalars().first()
    if dataset is None:
        raise ScoringDataError("No profiled dataset found in this series to score against.")
    return dataset


def _resolve_entity_id_column(base_profile_columns: list[dict], override: str | None = None) -> str | None:
    """A natural key like a county FIPS code may not be predictive and thus
    never selected as a candidate feature -- look across the base dataset's
    *full* profiled column list, not just candidate_features. Zero or more
    than one "id"-dtype column falls back to positional row index rather
    than guessing which one is the right entity identifier.

    `override` (a spec's explicit entity_id_column) takes precedence over
    that guess entirely -- it's the escape hatch for panel/repeated-
    observations data, where the entity column legitimately repeats across
    rows (e.g. a FIPS code in a county-year panel) and so never qualifies
    as dtype "id", which requires row-level uniqueness."""
    if override is not None:
        return override if any(c["name"] == override for c in base_profile_columns) else None

    id_columns = [c["name"] for c in base_profile_columns if c.get("dtype") == "id"]
    return id_columns[0] if len(id_columns) == 1 else None


async def build_scoring_dataframe(db: AsyncSession, spec: ModelingSpec) -> ScoringDataResult:
    base_dataset = await db.get(Dataset, spec.dataset_id)
    if base_dataset is None:
        raise ScoringDataError("The spec's base dataset no longer exists.")

    # Scoring-only: resolve to the most recently uploaded dataset in the
    # same series, if the base dataset is tagged into one. Retraining
    # deliberately does NOT do this -- it always uses spec.dataset_id
    # literally, so a retrain stays reproducible against the dataset the
    # user actually attached, never silently drifting to a newer upload.
    if base_dataset.series_id is not None:
        base_dataset = await _resolve_latest_in_series(db, base_dataset.series_id, spec.organization_id)

    base_profile = await get_latest_profile(db, base_dataset)
    if base_profile is None:
        raise ScoringDataError("The resolved dataset has not finished profiling yet.")

    entity_id_column = _resolve_entity_id_column(base_profile.columns, override=spec.entity_id_column)
    if spec.entity_id_column is not None and entity_id_column is None:
        raise ScoringDataError(
            f"This spec's entity_id_column '{spec.entity_id_column}' does not exist in the "
            "resolved dataset -- check the spec's setting or the dataset's columns."
        )

    needed = [*spec.candidate_features]
    if entity_id_column is not None and entity_id_column not in needed:
        needed.append(entity_id_column)

    try:
        df, _base_profile, _joins, _owner = await _materialize_join_columns(db, base_dataset, spec, needed)
    except TrainingDataError as exc:
        raise ScoringDataError(str(exc)) from exc

    if len(df) == 0:
        raise ScoringDataError("No rows to score -- check the resolved dataset and join keys.")

    warnings: list[str] = []
    for name in spec.candidate_features:
        null_rate = df[name].isna().mean()
        if null_rate > FEATURE_NULL_REJECT_THRESHOLD:
            raise ScoringDataError(f"Feature '{name}' is {null_rate:.0%} null -- unusable for scoring.")
        if null_rate > FEATURE_NULL_WARN_THRESHOLD:
            warnings.append(f"Feature '{name}' is {null_rate:.0%} null; missing values will be imputed.")

    if entity_id_column is not None:
        entity_ids = df[entity_id_column].astype(str).tolist()
    else:
        entity_ids = [str(i) for i in range(len(df))]

    score_date = base_dataset.as_of_date or date.today()

    return ScoringDataResult(
        dataframe=df,
        entity_ids=entity_ids,
        resolved_dataset_id=base_dataset.id,
        score_date=score_date,
        warnings=warnings,
        row_count=len(df),
    )
