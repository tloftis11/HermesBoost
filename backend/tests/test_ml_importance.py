import numpy as np
import pytest

from app.services.ml.importance import extract_feature_importance, get_raw_importances


class _FakeTreeEstimator:
    def __init__(self, importances):
        self.feature_importances_ = np.array(importances)


class _FakeLinearEstimator:
    def __init__(self, coef):
        self.coef_ = np.array(coef)


def test_get_raw_importances_prefers_feature_importances_over_coef():
    estimator = _FakeTreeEstimator([0.1, 0.9])
    assert list(get_raw_importances(estimator)) == [0.1, 0.9]


def test_get_raw_importances_from_1d_coef():
    estimator = _FakeLinearEstimator([1.0, -2.0, 3.0])
    assert list(get_raw_importances(estimator)) == [1.0, 2.0, 3.0]


def test_get_raw_importances_from_2d_coef_averages_across_classes():
    estimator = _FakeLinearEstimator([[1.0, -2.0, 3.0], [-1.0, 2.0, -3.0]])
    assert list(get_raw_importances(estimator)) == [1.0, 2.0, 3.0]


def test_get_raw_importances_raises_for_unsupported_estimator():
    with pytest.raises(NotImplementedError):
        get_raw_importances(object())


def test_extract_feature_importance_aggregates_onehot_columns_and_normalizes():
    # index 0 -> numeric "num_a"; indices 1-3 -> one-hot expansion of "cat_b"
    estimator = _FakeTreeEstimator([0.4, 0.1, 0.2, 0.3])
    output_feature_map = {0: "num_a", 1: "cat_b", 2: "cat_b", 3: "cat_b"}

    result = extract_feature_importance(estimator, output_feature_map)

    assert sum(r["importance"] for r in result) == pytest.approx(1.0)
    by_feature = {r["feature"]: r["importance"] for r in result}
    assert by_feature["cat_b"] == pytest.approx(0.6)
    assert by_feature["num_a"] == pytest.approx(0.4)
    # sorted descending
    assert [r["feature"] for r in result] == ["cat_b", "num_a"]


def test_extract_feature_importance_caps_to_top_n():
    estimator = _FakeTreeEstimator([0.4, 0.3, 0.2, 0.1])
    output_feature_map = {0: "a", 1: "b", 2: "c", 3: "d"}

    result = extract_feature_importance(estimator, output_feature_map, top_n=2)

    assert [r["feature"] for r in result] == ["a", "b"]
