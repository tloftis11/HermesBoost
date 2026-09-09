"""Builds a clean, ready-to-train pandas DataFrame from a modeling spec (+ 0+
ModelingSpecJoinDataset rows), materializing any join via DuckDB the same
way profiling.py scans CSVs -- inline read_csv_auto() calls over temp files,
never a persistent DuckDB table.

TrainingDataError is raised for anything that would silently corrupt a
model (bad join key, ambiguous column, unusable data); everything else that
merely deserves a heads-up is appended to TrainingDataResult.warnings and
training proceeds.
"""

import os
import tempfile

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.models.modeling_spec import ModelingSpec
from app.models.modeling_spec_join_dataset import ModelingSpecJoinDataset
from app.services.dataset_profiles import get_latest_profile
from app.services.profiling import _quote_ident
from app.services.storage import get_storage_backend

MIN_ROWS = 20
FEATURE_NULL_REJECT_THRESHOLD = 0.90
FEATURE_NULL_WARN_THRESHOLD = 0.05
INNER_JOIN_ROW_RETENTION_REJECT = 0.5
INNER_JOIN_ROW_RETENTION_WARN = 0.9
LEFT_JOIN_NULL_INCREASE_WARN = 0.05


class TrainingDataError(Exception):
    pass


class TrainingDataResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataframe: pd.DataFrame
    feature_dtypes: dict[str, str]  # {column: "numeric" | "categorical"}
    row_count: int
    warnings: list[str]


async def _materialize_join_columns(
    db: AsyncSession, base_dataset: Dataset, spec: ModelingSpec, needed_columns: list[str]
) -> tuple[pd.DataFrame, DatasetProfile, list[dict], dict[str, str]]:
    """Resolves the spec's join rows against base_dataset, validates join
    keys and column-name collisions, downloads everything to temp files,
    and executes one DuckDB query selecting `needed_columns`. Shared by
    build_training_dataframe and scoring_data.build_scoring_dataframe --
    only what happens to the result afterward (target handling, dtype/
    warning bookkeeping) differs between the two.

    base_dataset is an explicit parameter rather than looked up from
    spec.dataset_id so scoring can pass a series-resolved dataset instead
    of the spec's literal base dataset.

    Returns (dataframe, base_profile, joins, owner)."""
    base_profile = await get_latest_profile(db, base_dataset)
    if base_profile is None:
        raise TrainingDataError("The base dataset has not finished profiling yet.")

    join_rows = (
        await db.execute(
            select(ModelingSpecJoinDataset).where(
                ModelingSpecJoinDataset.modeling_spec_id == spec.id
            )
        )
    ).scalars().all()

    joins = []
    for jr in join_rows:
        if jr.join_type not in ("inner", "left"):
            raise TrainingDataError(f"Unsupported join_type '{jr.join_type}'.")
        joined_dataset = await db.get(Dataset, jr.dataset_id)
        if joined_dataset is None:
            raise TrainingDataError(f"Joined dataset {jr.dataset_id} no longer exists.")
        joined_profile = await get_latest_profile(db, joined_dataset)
        if joined_profile is None:
            raise TrainingDataError(f"Joined dataset '{joined_dataset.name}' has not finished profiling yet.")
        joined_columns = {c["name"]: c for c in joined_profile.columns}
        if jr.join_key_column not in joined_columns:
            raise TrainingDataError(
                f"Join key '{jr.join_key_column}' is not a real column of dataset '{joined_dataset.name}'."
            )
        joins.append({"row": jr, "dataset": joined_dataset, "profile": joined_profile, "columns": joined_columns})

    base_columns = {c["name"]: c for c in base_profile.columns}
    for j in joins:
        if j["row"].join_key_column not in base_columns:
            raise TrainingDataError(
                f"Join key '{j['row'].join_key_column}' is not a real column of the base dataset."
            )

    # Column ownership + collision check. The join key is expected to exist
    # on both sides of a join by design, so it's excluded from the collision
    # check; any other non-key name appearing in more than one dataset is
    # ambiguous, since candidate_features aren't qualified by source dataset.
    owner: dict[str, str] = dict.fromkeys(base_columns, "base")
    for i, j in enumerate(joins):
        alias = f"join_{i}"
        key = j["row"].join_key_column
        for name in j["columns"]:
            if name == key:
                continue
            if name in owner:
                raise TrainingDataError(
                    f"Column '{name}' exists in more than one attached dataset. "
                    "Candidate features aren't qualified by source dataset, so this is ambiguous."
                )
            owner[name] = alias

    for name in needed_columns:
        if name not in owner:
            raise TrainingDataError(f"Column '{name}' was not found in the base or any attached dataset.")

    tmp_paths: list[str] = []
    try:
        base_path = _download_to_tempfile(base_dataset)
        tmp_paths.append(base_path)
        aliases = {"base": base_path.replace("\\", "/")}
        for i, j in enumerate(joins):
            path = _download_to_tempfile(j["dataset"])
            tmp_paths.append(path)
            aliases[f"join_{i}"] = path.replace("\\", "/")

        con = duckdb.connect(":memory:")
        from_clause = f"read_csv_auto('{aliases['base']}') as base"
        join_clauses = []
        for i, j in enumerate(joins):
            alias = f"join_{i}"
            key_q = _quote_ident(j["row"].join_key_column)
            join_kind = "LEFT" if j["row"].join_type == "left" else "INNER"
            join_clauses.append(
                f"{join_kind} JOIN read_csv_auto('{aliases[alias]}') as {alias} "
                f"ON base.{key_q} = {alias}.{key_q}"
            )

        # dedupe (needed_columns could repeat a name) while preserving
        # order, then select each once from its owning source
        seen: set[str] = set()
        select_cols = []
        for name in needed_columns:
            if name in seen:
                continue
            seen.add(name)
            select_cols.append(f'{owner[name]}.{_quote_ident(name)} as {_quote_ident(name)}')

        sql = f"SELECT {', '.join(select_cols)} FROM {from_clause} {' '.join(join_clauses)}"
        df: pd.DataFrame = con.sql(sql).df()
    finally:
        for p in tmp_paths:
            os.unlink(p)

    return df, base_profile, joins, owner


async def build_training_dataframe(db: AsyncSession, spec: ModelingSpec) -> TrainingDataResult:
    base_dataset = await db.get(Dataset, spec.dataset_id)
    if base_dataset is None:
        raise TrainingDataError("The spec's base dataset no longer exists.")

    needed = [spec.target, *spec.candidate_features]
    df, base_profile, joins, owner = await _materialize_join_columns(db, base_dataset, spec, needed)

    warnings: list[str] = []
    has_inner_join = any(j["row"].join_type == "inner" for j in joins)

    if len(df) == 0:
        raise TrainingDataError("The joined result has zero rows -- check the join keys.")
    if has_inner_join:
        retention = len(df) / base_profile.row_count if base_profile.row_count else 0
        if retention < INNER_JOIN_ROW_RETENTION_REJECT:
            raise TrainingDataError(
                f"The inner join retained only {retention:.0%} of the base dataset's rows -- "
                "this usually means the join key doesn't match as expected, not normal attrition."
            )
        if retention < INNER_JOIN_ROW_RETENTION_WARN:
            warnings.append(f"The inner join dropped {1 - retention:.0%} of the base dataset's rows.")

    target_null_rate = df[spec.target].isna().mean()
    if target_null_rate >= 1.0:
        raise TrainingDataError(f"Target column '{spec.target}' is entirely null after the join.")
    df = df.dropna(subset=[spec.target])
    if len(df) < MIN_ROWS:
        raise TrainingDataError(
            f"Only {len(df)} rows remain after dropping null targets -- "
            f"at least {MIN_ROWS} are needed for a meaningful train/test split."
        )

    feature_dtypes: dict[str, str] = {}
    for name in spec.candidate_features:
        # Determined from the materialized dataframe's real pandas dtype,
        # not the stored profile's dtype label -- a profile classifies an
        # all-distinct numeric column as "id" (e.g. a naturally-unique
        # measurement), which isn't "numeric" or "categorical", and treating
        # it as categorical crashes the imputer (tries to fill a float64
        # column with the string "__missing__").
        feature_dtypes[name] = "numeric" if pd.api.types.is_numeric_dtype(df[name]) else "categorical"

        null_rate = df[name].isna().mean()
        if null_rate > FEATURE_NULL_REJECT_THRESHOLD:
            raise TrainingDataError(f"Feature '{name}' is {null_rate:.0%} null -- unusable.")
        if null_rate > FEATURE_NULL_WARN_THRESHOLD:
            warnings.append(f"Feature '{name}' is {null_rate:.0%} null; missing values will be imputed.")

        owner_alias = owner[name]
        if owner_alias != "base":
            join_idx = int(owner_alias.split("_")[1])
            join_type = joins[join_idx]["row"].join_type
            if join_type == "left":
                original_null_rate = joins[join_idx]["columns"][name]["null_rate"]
                if null_rate - original_null_rate > LEFT_JOIN_NULL_INCREASE_WARN:
                    warnings.append(
                        f"Feature '{name}' gained additional nulls from the left join "
                        "(possible key mismatches)."
                    )

    return TrainingDataResult(
        dataframe=df,
        feature_dtypes=feature_dtypes,
        row_count=len(df),
        warnings=warnings,
    )


def _download_to_tempfile(dataset: Dataset) -> str:
    data = get_storage_backend().download(dataset.storage_bucket, dataset.storage_path)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(data)
        return tmp.name
