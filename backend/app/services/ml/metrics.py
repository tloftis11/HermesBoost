"""Per-task metric computation. Classification always includes expected
calibration error for risk_scoring specs (a risk score is meaningless
uncalibrated) and opportunistically for plain classification specs too,
since it's cheap to compute regardless."""

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    precision_recall_curve,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)

CALIBRATION_BINS = 10


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = CALIBRATION_BINS) -> float:
    """y_prob: (n_samples, n_classes) predicted probabilities. Bins by each
    sample's max predicted-class confidence, compares mean confidence vs.
    accuracy (argmax == y_true) per bin, weighted by bin count -- one
    formula works for both binary and multiclass."""
    y_true = np.asarray(y_true)
    confidence = y_prob.max(axis=1)
    predicted = y_prob.argmax(axis=1)
    correct = (predicted == y_true).astype(float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = len(confidence)
    ece = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        in_bin = (confidence > lo) & (confidence <= hi) if lo > 0 else (confidence >= lo) & (confidence <= hi)
        count = in_bin.sum()
        if count == 0:
            continue
        bin_confidence = confidence[in_bin].mean()
        bin_accuracy = correct[in_bin].mean()
        ece += (count / n) * abs(bin_confidence - bin_accuracy)
    return float(ece)


def _f1_optimal_threshold(y_true: np.ndarray, y_prob_positive: np.ndarray) -> dict:
    """The argmax-based precision/recall (implicit 0.5 threshold) is nearly
    meaningless when the positive class is rare -- a model can score well
    on ranking (AUC) while never actually crossing 0.5. This searches the
    full precision-recall curve for the threshold that maximizes F1, a
    second, far more informative operating point to report alongside the
    standard one."""
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob_positive)
    # precision_recall_curve returns one more precision/recall pair than
    # thresholds (the last pair corresponds to an implicit threshold of
    # infinity) -- drop it so the arrays line up.
    precisions, recalls = precisions[:-1], recalls[:-1]
    f1_scores = np.where(
        (precisions + recalls) > 0, 2 * precisions * recalls / (precisions + recalls + 1e-12), 0.0
    )
    if len(f1_scores) == 0:
        return {"threshold_at_max_f1": None, "precision_at_max_f1": None, "recall_at_max_f1": None}
    best = int(np.argmax(f1_scores))
    return {
        "threshold_at_max_f1": round(float(thresholds[best]), 4),
        "precision_at_max_f1": round(float(precisions[best]), 4),
        "recall_at_max_f1": round(float(recalls[best]), 4),
    }


def compute_classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray, class_weighted: bool = False
) -> dict:
    n_classes = y_prob.shape[1]
    extra: dict = {}
    if n_classes == 2:
        auc = roc_auc_score(y_true, y_prob[:, 1])
        precision = precision_score(y_true, y_pred, average="binary", zero_division=0)
        recall = recall_score(y_true, y_pred, average="binary", zero_division=0)
        extra = _f1_optimal_threshold(y_true, y_prob[:, 1])
    else:
        auc = roc_auc_score(y_true, y_prob, multi_class="ovr", average="macro")
        precision = precision_score(y_true, y_pred, average="macro", zero_division=0)
        recall = recall_score(y_true, y_pred, average="macro", zero_division=0)

    return {
        "auc": round(float(auc), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "calibration_error": round(expected_calibration_error(y_true, y_prob), 4),
        "class_weighted": class_weighted,
        **extra,
    }


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "rmse": round(float(root_mean_squared_error(y_true, y_pred)), 4),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }
