"""Pure DuckDB profiling logic -- no network calls, no DB writes.

Given raw CSV bytes, returns a JSON-shaped profile dict:
{row_count, column_count, columns: [{name, dtype, null_rate, distinct_count,
min, max, mean, top_values, histogram}]}

This is deliberately side-effect-free (beyond a scratch temp file DuckDB
needs to scan) so it's directly unit-testable against fixture CSVs.
"""

import csv
import io
import os
import tempfile

import duckdb

NUMERIC_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
}

HISTOGRAM_BUCKETS = 8
TOP_VALUES_LIMIT = 5


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def profile_csv_bytes(data: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    csv_path = tmp_path.replace("\\", "/")

    try:
        con = duckdb.connect(database=":memory:")
        rel = con.read_csv(tmp_path)
        row_count = rel.aggregate("count(*) as n").fetchone()[0] or 0
        col_names = rel.columns
        col_types = [str(t) for t in rel.types]

        columns = []
        for col_name, col_type in zip(col_names, col_types, strict=True):
            columns.append(
                _profile_column(con, csv_path, col_name, col_type, row_count)
            )

        return {
            "row_count": row_count,
            "column_count": len(col_names),
            "columns": columns,
        }
    finally:
        os.unlink(tmp_path)


def _profile_column(con, csv_path: str, col_name: str, col_type: str, row_count: int) -> dict:
    q = _quote_ident(col_name)
    base_type = col_type.split("(")[0].upper()
    is_numeric = base_type in NUMERIC_TYPES

    distinct_count, null_count = con.sql(
        f"""
        select count(distinct {q}), sum(case when {q} is null then 1 else 0 end)
        from read_csv_auto('{csv_path}')
        """
    ).fetchone()
    distinct_count = distinct_count or 0
    null_count = null_count or 0
    null_rate = (null_count / row_count) if row_count else 0.0

    if row_count > 0 and distinct_count == row_count:
        dtype = "id"
    elif is_numeric:
        dtype = "numeric"
    else:
        dtype = "categorical"

    profile = {
        "name": col_name,
        "dtype": dtype,
        "null_rate": round(null_rate, 4),
        "distinct_count": distinct_count,
        "min": None,
        "max": None,
        "mean": None,
        "top_values": None,
        "histogram": None,
    }

    if dtype == "numeric":
        mn, mx, avgv = con.sql(
            f"select min({q}), max({q}), avg({q}) from read_csv_auto('{csv_path}')"
        ).fetchone()
        profile["min"] = float(mn) if mn is not None else None
        profile["max"] = float(mx) if mx is not None else None
        profile["mean"] = float(avgv) if avgv is not None else None
        profile["histogram"] = _histogram(con, csv_path, q, profile["min"], profile["max"])
    elif dtype == "categorical":
        profile["top_values"] = _top_values(con, csv_path, q)

    return profile


def _histogram(con, csv_path: str, quoted_col: str, mn: float | None, mx: float | None) -> list[int]:
    buckets = [0] * HISTOGRAM_BUCKETS
    if mn is None or mx is None:
        return buckets

    span = mx - mn
    if span == 0:
        total = con.sql(
            f"select count(*) from read_csv_auto('{csv_path}') where {quoted_col} is not null"
        ).fetchone()[0]
        buckets[0] = total or 0
        return buckets

    rows = con.sql(
        f"""
        select least(cast(floor(({quoted_col} - {mn}) / ({span}) * {HISTOGRAM_BUCKETS}) as integer), {HISTOGRAM_BUCKETS - 1}) as bucket,
               count(*) as c
        from read_csv_auto('{csv_path}')
        where {quoted_col} is not null
        group by bucket
        """
    ).fetchall()
    for bucket, c in rows:
        if bucket is not None and 0 <= bucket < HISTOGRAM_BUCKETS:
            buckets[bucket] += c
    return buckets


def _top_values(con, csv_path: str, quoted_col: str) -> list[dict]:
    rows = con.sql(
        f"""
        select {quoted_col} as v, count(*) as c
        from read_csv_auto('{csv_path}')
        where {quoted_col} is not null
        group by v
        order by c desc
        limit {TOP_VALUES_LIMIT}
        """
    ).fetchall()
    return [{"value": str(v), "count": c} for v, c in rows]


def sample_rows(data: bytes, limit: int = 10) -> list[dict]:
    """First `limit` rows as dicts, for LLM prompt context -- never the full file."""
    text = data.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        if i >= limit:
            break
        rows.append(row)
    return rows
