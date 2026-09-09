import numpy as np

from app.services.ml.train import _json_safe


def test_json_safe_maps_numpy_nan_to_none():
    # XGBoost's sklearn wrapper defaults `missing` to np.nan -- json.dumps
    # emits the literal (non-JSON-spec) token `NaN`, which Postgres's JSONB
    # column rejects outright. This is the real bug caught during the
    # milestone 3 live-mode verification run.
    assert _json_safe({"missing": np.float64("nan")}) == {"missing": None}


def test_json_safe_maps_native_nan_and_inf_to_none():
    assert _json_safe({"a": float("nan"), "b": float("inf"), "c": float("-inf")}) == {
        "a": None,
        "b": None,
        "c": None,
    }


def test_json_safe_converts_numpy_scalars_to_native_types():
    result = _json_safe({"c": np.float64(3.5), "n": np.int64(200), "flag": np.bool_(True)})
    assert result == {"c": 3.5, "n": 200, "flag": True}
    assert isinstance(result["c"], float)
    assert isinstance(result["n"], int)
    assert isinstance(result["flag"], bool)


def test_json_safe_recurses_through_lists_and_nested_dicts():
    value = {"items": [{"x": np.float64("nan")}, {"x": 1.0}]}
    assert _json_safe(value) == {"items": [{"x": None}, {"x": 1.0}]}


def test_json_safe_passes_through_plain_values_unchanged():
    assert _json_safe({"name": "logistic_regression", "flag": None}) == {
        "name": "logistic_regression",
        "flag": None,
    }
