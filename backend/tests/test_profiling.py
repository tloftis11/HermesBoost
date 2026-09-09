from app.services.profiling import profile_csv_bytes, sample_rows


def test_small_sample_shape(fixtures_dir):
    data = (fixtures_dir / "small_sample.csv").read_bytes()
    profile = profile_csv_bytes(data)

    assert profile["row_count"] == 3
    assert profile["column_count"] == 3
    names = {c["name"] for c in profile["columns"]}
    assert names == {"id", "name", "score"}


def test_id_column_detected(fixtures_dir):
    data = (fixtures_dir / "types_sample.csv").read_bytes()
    profile = profile_csv_bytes(data)
    columns = {c["name"]: c for c in profile["columns"]}

    assert columns["row_id"]["dtype"] == "id"
    assert columns["row_id"]["distinct_count"] == 6


def test_numeric_column_stats_and_null_rate(fixtures_dir):
    data = (fixtures_dir / "types_sample.csv").read_bytes()
    profile = profile_csv_bytes(data)
    columns = {c["name"]: c for c in profile["columns"]}

    amount = columns["amount"]
    assert amount["dtype"] == "numeric"
    assert amount["min"] == 10.5
    assert amount["max"] == 30.0
    assert amount["null_rate"] == round(1 / 6, 4)
    assert amount["histogram"] is not None
    assert len(amount["histogram"]) == 8
    assert sum(amount["histogram"]) == 5  # 5 non-null values


def test_categorical_top_values(fixtures_dir):
    data = (fixtures_dir / "types_sample.csv").read_bytes()
    profile = profile_csv_bytes(data)
    columns = {c["name"]: c for c in profile["columns"]}

    category = columns["category"]
    assert category["dtype"] == "categorical"
    top = {tv["value"]: tv["count"] for tv in category["top_values"]}
    assert top == {"A": 3, "B": 2, "C": 1}


def test_sample_rows_capped(fixtures_dir):
    data = (fixtures_dir / "types_sample.csv").read_bytes()
    rows = sample_rows(data, limit=2)
    assert len(rows) == 2
    assert rows[0]["row_id"] == "1"
