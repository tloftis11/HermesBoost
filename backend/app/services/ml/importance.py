"""Uniform feature-importance extraction across every leaderboard estimator
type (logistic/linear regression, random forest, XGBoost, and whatever FLAML
picked -- lgbm/rf/xgboost/extra_tree/lrl1, all of which expose either
feature_importances_ or coef_)."""

import numpy as np

TOP_N_DEFAULT = 15


def get_raw_importances(estimator) -> np.ndarray:
    if hasattr(estimator, "feature_importances_"):
        return np.asarray(estimator.feature_importances_)
    if hasattr(estimator, "coef_"):
        coef = np.abs(np.asarray(estimator.coef_))
        return coef.mean(axis=0) if coef.ndim > 1 else coef
    raise NotImplementedError(
        f"no importance extraction available for estimator type {type(estimator).__name__}"
    )


def extract_feature_importance(
    estimator, output_feature_map: dict[int, str], top_n: int = TOP_N_DEFAULT
) -> list[dict]:
    """Aggregates one-hot-expanded output columns back to their original
    candidate feature (summed -- best represents that column's total
    contribution), normalizes to sum to 1.0, sorted descending, capped to
    top_n. Returns [{"feature": str, "importance": float}, ...] -- the same
    shape consumed by the leaderboard API and the LLM interpretation prompt.
    """
    raw = get_raw_importances(estimator)

    by_feature: dict[str, float] = {}
    for idx, value in enumerate(raw):
        feature = output_feature_map.get(idx)
        if feature is None:
            continue
        by_feature[feature] = by_feature.get(feature, 0.0) + float(value)

    total = sum(by_feature.values())
    if total > 0:
        by_feature = {k: v / total for k, v in by_feature.items()}

    ranked = sorted(by_feature.items(), key=lambda kv: kv[1], reverse=True)
    return [{"feature": name, "importance": round(value, 6)} for name, value in ranked[:top_n]]
