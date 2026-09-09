from app.services.ml.imbalance import IMBALANCE_THRESHOLD, is_imbalanced, minority_rate


def test_minority_rate_balanced():
    assert minority_rate({"a": 50, "b": 50}) == 0.5


def test_minority_rate_imbalanced():
    assert minority_rate({"False": 928, "True": 64}) == 64 / 992


def test_minority_rate_empty_counts_is_one():
    assert minority_rate({}) == 1.0


def test_is_imbalanced_below_threshold():
    assert is_imbalanced(0.05) is True


def test_is_imbalanced_above_threshold():
    assert is_imbalanced(0.5) is False


def test_is_imbalanced_at_threshold_boundary():
    # Strictly less-than -- exactly at the threshold does not count as imbalanced.
    assert is_imbalanced(IMBALANCE_THRESHOLD) is False
