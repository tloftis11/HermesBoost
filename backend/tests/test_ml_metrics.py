import numpy as np
import pytest

from app.services.ml.metrics import (
    compute_classification_metrics,
    compute_regression_metrics,
    expected_calibration_error,
)


def test_expected_calibration_error_known_example():
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([[0.9, 0.1], [0.6, 0.4], [0.3, 0.7], [0.2, 0.8]])

    ece = expected_calibration_error(y_true, y_prob)

    assert ece == pytest.approx(0.25, abs=1e-9)


def test_expected_calibration_error_perfectly_calibrated_is_zero():
    # confidence always 0.5 in a binary problem -> accuracy of a coin flip
    # matches confidence exactly when every prediction is "correct" at 0.5
    y_true = np.array([1, 1, 1, 1])
    y_prob = np.array([[0.0, 1.0]] * 4)

    ece = expected_calibration_error(y_true, y_prob)

    assert ece == pytest.approx(0.0, abs=1e-9)


def test_compute_classification_metrics_binary():
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 1, 1, 1])
    y_prob = np.array([[0.9, 0.1], [0.6, 0.4], [0.3, 0.7], [0.2, 0.8]])

    metrics = compute_classification_metrics(y_true, y_pred, y_prob)

    assert metrics == {
        "auc": 1.0,
        "precision": 0.6667,
        "recall": 1.0,
        "accuracy": 0.75,
        "calibration_error": 0.25,
        "class_weighted": False,
        "threshold_at_max_f1": 0.7,
        "precision_at_max_f1": 1.0,
        "recall_at_max_f1": 1.0,
    }


def test_compute_classification_metrics_class_weighted_flag_passes_through():
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 1, 1, 1])
    y_prob = np.array([[0.9, 0.1], [0.6, 0.4], [0.3, 0.7], [0.2, 0.8]])

    metrics = compute_classification_metrics(y_true, y_pred, y_prob, class_weighted=True)

    assert metrics["class_weighted"] is True


def test_compute_regression_metrics():
    y_true = np.array([3.0, -1.0, 2.0, 5.0])
    y_pred = np.array([2.5, -1.5, 2.0, 4.0])

    metrics = compute_regression_metrics(y_true, y_pred)

    assert metrics == {"rmse": 0.6124, "mae": 0.5, "r2": 0.92}
