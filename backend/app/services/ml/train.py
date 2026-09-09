"""The leaderboard: one FLAML-searched "recommended" candidate + three
fixed-hyperparameter baselines, all fit on the exact same preprocessed
matrix so metrics and feature importance stay comparable across the board.

Extracting FLAML's internal per-estimator trial history was considered and
rejected -- those are undocumented, version-fragile internals. This hybrid
is simpler, more testable, and gives exactly the ~4-row leaderboard the
mockup wants.
"""

import time
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from flaml import AutoML
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier, XGBRegressor

from app.services.ml.importance import extract_feature_importance
from app.services.ml.metrics import compute_classification_metrics, compute_regression_metrics
from app.services.ml.task_mapping import MlTask
from app.services.ml.training_data import TrainingDataError, TrainingDataResult

TEST_SIZE = 0.2
RANDOM_STATE = 42

BASELINE_ESTIMATORS = {
    "classification": {
        "logistic_regression": lambda: LogisticRegression(max_iter=1000),
        "random_forest": lambda: RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE),
        "xgboost": lambda: XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.1, eval_metric="logloss", random_state=RANDOM_STATE
        ),
    },
    "regression": {
        "linear_regression": lambda: LinearRegression(),
        "random_forest": lambda: RandomForestRegressor(n_estimators=200, random_state=RANDOM_STATE),
        "xgboost": lambda: XGBRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.1, random_state=RANDOM_STATE
        ),
    },
}


@dataclass
class Candidate:
    role: str  # "recommended" | "baseline"
    algorithm: str
    estimator: object  # fitted, unwrapped sklearn/xgboost-compatible object
    hyperparams: dict
    train_time_seconds: float
    metrics: dict
    feature_importance: list[dict]


@dataclass
class SplitData:
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: np.ndarray
    y_test: np.ndarray
    label_classes: list[str] | None


def split_and_encode(data: TrainingDataResult, spec, ml_task: MlTask) -> SplitData:
    df = data.dataframe
    X = df[spec.candidate_features]
    y_raw = df[spec.target]

    label_classes = None
    if ml_task == "classification":
        counts = y_raw.value_counts()
        too_small = counts[counts < 2]
        if len(too_small) > 0:
            raise TrainingDataError(
                f"Target class(es) with fewer than 2 examples: {too_small.index.tolist()} -- "
                "cannot reliably train or evaluate on them."
            )
        encoder = LabelEncoder()
        y = encoder.fit_transform(y_raw)
        label_classes = [str(c) for c in encoder.classes_]
    else:
        y = y_raw.astype(float).to_numpy()

    stratify = y if ml_task == "classification" else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=stratify
    )
    return SplitData(X_train, X_test, y_train, y_test, label_classes)


def _estimator_list(ml_task: MlTask) -> list[str]:
    if ml_task == "classification":
        return ["lgbm", "rf", "xgboost", "extra_tree", "lrl1"]
    return ["lgbm", "rf", "xgboost", "extra_tree"]


def _flaml_metric_for(ml_task: MlTask) -> str:
    return "roc_auc" if ml_task == "classification" else "r2"


def _json_safe(value):
    """Coerces numpy scalar types (which FLAML's best_config and sklearn's
    get_params() can return) into plain Python types so the result can be
    stored directly as JSONB."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _compute_metrics(estimator, ml_task: MlTask, X_test, y_test) -> dict:
    if ml_task == "classification":
        y_prob = estimator.predict_proba(X_test)
        y_pred = y_prob.argmax(axis=1)
        return compute_classification_metrics(y_test, y_pred, y_prob)
    y_pred = estimator.predict(X_test)
    return compute_regression_metrics(y_test, y_pred)


def fit_flaml_candidate(
    X_train, y_train, X_test, y_test, ml_task: MlTask, time_budget: int, output_feature_map: dict
) -> Candidate:
    start = time.monotonic()
    automl = AutoML()
    with warnings.catch_warnings():
        # FLAML 2.6's lrl1 estimator uses a sklearn LogisticRegression
        # `penalty` kwarg deprecated in sklearn 1.9 -- noisy, not fatal.
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=UserWarning)
        automl.fit(
            X_train=X_train,
            y_train=y_train,
            task=ml_task,
            time_budget=time_budget,
            metric=_flaml_metric_for(ml_task),
            estimator_list=_estimator_list(ml_task),
            seed=RANDOM_STATE,
            verbose=0,
        )
    elapsed = time.monotonic() - start
    estimator = automl.model.estimator
    return Candidate(
        role="recommended",
        algorithm=f"flaml_{automl.best_estimator}",
        estimator=estimator,
        hyperparams=_json_safe(dict(automl.best_config)),
        train_time_seconds=elapsed,
        metrics=_compute_metrics(estimator, ml_task, X_test, y_test),
        feature_importance=extract_feature_importance(estimator, output_feature_map),
    )


def fit_baseline_candidate(
    name: str, factory, X_train, y_train, X_test, y_test, ml_task: MlTask, output_feature_map: dict
) -> Candidate:
    start = time.monotonic()
    estimator = factory()
    estimator.fit(X_train, y_train)
    elapsed = time.monotonic() - start
    return Candidate(
        role="baseline",
        algorithm=name,
        estimator=estimator,
        hyperparams=_json_safe(estimator.get_params()),
        train_time_seconds=elapsed,
        metrics=_compute_metrics(estimator, ml_task, X_test, y_test),
        feature_importance=extract_feature_importance(estimator, output_feature_map),
    )


def fit_all_candidates(
    X_train, y_train, X_test, y_test, ml_task: MlTask, time_budget: int, output_feature_map: dict
) -> list[Candidate]:
    recommended = fit_flaml_candidate(X_train, y_train, X_test, y_test, ml_task, time_budget, output_feature_map)
    baselines = [
        fit_baseline_candidate(name, factory, X_train, y_train, X_test, y_test, ml_task, output_feature_map)
        for name, factory in BASELINE_ESTIMATORS[ml_task].items()
    ]
    # FLAML's pick is always its own leaderboard row, even if it lands on the
    # same algorithm family as a baseline (e.g. both "rf") -- tuned-via-search
    # vs. fixed-defaults are two distinct comparisons, not a duplicate.
    return [recommended, *baselines]
