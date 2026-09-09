import pandas as pd

from app.services.ml.preprocessing import build_preprocessor, get_output_feature_map, split_dtype_columns


def test_split_dtype_columns_preserves_order():
    feature_dtypes = {"b": "categorical", "a": "numeric", "c": "categorical", "d": "numeric"}
    numeric_cols, categorical_cols = split_dtype_columns(feature_dtypes)
    assert numeric_cols == ["a", "d"]
    assert categorical_cols == ["b", "c"]


def test_build_preprocessor_transforms_expected_shape():
    df = pd.DataFrame({
        "num_a": [1.0, 2.0, None, 4.0],
        "cat_b": ["x", "y", "x", None],
    })
    numeric_cols, categorical_cols = split_dtype_columns({"num_a": "numeric", "cat_b": "categorical"})
    preprocessor = build_preprocessor(numeric_cols, categorical_cols)

    transformed = preprocessor.fit_transform(df)
    # 1 numeric column + one-hot of {x, y, __missing__} = 3 categorical columns
    assert transformed.shape == (4, 4)


def test_get_output_feature_map_aggregates_onehot_back_to_source():
    df = pd.DataFrame({
        "num_a": [1.0, 2.0, 3.0],
        "cat_b": ["x", "y", "z"],
    })
    numeric_cols, categorical_cols = split_dtype_columns({"num_a": "numeric", "cat_b": "categorical"})
    preprocessor = build_preprocessor(numeric_cols, categorical_cols)
    preprocessor.fit(df)

    feature_map = get_output_feature_map(preprocessor, numeric_cols, categorical_cols)

    # index 0 -> num_a; indices 1-3 -> the 3 one-hot columns for cat_b, x/y/z
    assert feature_map[0] == "num_a"
    assert feature_map[1] == "cat_b"
    assert feature_map[2] == "cat_b"
    assert feature_map[3] == "cat_b"
    assert len(feature_map) == 4


def test_get_output_feature_map_numeric_only():
    df = pd.DataFrame({"num_a": [1.0, 2.0], "num_b": [3.0, 4.0]})
    numeric_cols, categorical_cols = split_dtype_columns({"num_a": "numeric", "num_b": "numeric"})
    preprocessor = build_preprocessor(numeric_cols, categorical_cols)
    preprocessor.fit(df)

    feature_map = get_output_feature_map(preprocessor, numeric_cols, categorical_cols)
    assert feature_map == {0: "num_a", 1: "num_b"}
