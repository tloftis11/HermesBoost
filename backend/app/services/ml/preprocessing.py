"""Shared preprocessing: one ColumnTransformer fit once and applied
identically ahead of every leaderboard candidate (the FLAML-searched one
included), so the leaderboard is apples-to-apples and feature importances
can be aggregated back to original column names the same way regardless of
which estimator produced them.

Missing values: numeric -> median impute (robust to skew); categorical ->
a "__missing__" sentinel category rather than most-frequent, since
missingness itself is frequently predictive.
"""

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def split_dtype_columns(feature_dtypes: dict[str, str]) -> tuple[list[str], list[str]]:
    """Returns (numeric_cols, categorical_cols), preserving feature_dtypes'
    insertion order -- callers must reuse these same two lists (not re-derive
    them) when building the output-feature map, so indices stay in sync."""
    numeric_cols = [c for c, t in feature_dtypes.items() if t == "numeric"]
    categorical_cols = [c for c, t in feature_dtypes.items() if t != "numeric"]
    return numeric_cols, categorical_cols


def build_preprocessor(numeric_cols: list[str], categorical_cols: list[str]) -> ColumnTransformer:
    transformers = []
    if numeric_cols:
        transformers.append((
            "num",
            Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]),
            numeric_cols,
        ))
    if categorical_cols:
        transformers.append((
            "cat",
            Pipeline([
                ("impute", SimpleImputer(strategy="constant", fill_value="__missing__")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]),
            categorical_cols,
        ))
    return ColumnTransformer(transformers)


def get_output_feature_map(
    preprocessor: ColumnTransformer, numeric_cols: list[str], categorical_cols: list[str]
) -> dict[int, str]:
    """Maps each column index of the *transformed* matrix back to its
    original candidate-feature name (a one-hot expansion collapses back to
    its source column) -- built from categories_ lengths rather than parsing
    get_feature_names_out() strings, so it's robust to column names that
    themselves contain underscores."""
    mapping: dict[int, str] = {}
    idx = 0
    for col in numeric_cols:
        mapping[idx] = col
        idx += 1
    if categorical_cols:
        onehot: OneHotEncoder = preprocessor.named_transformers_["cat"].named_steps["onehot"]
        for col, categories in zip(categorical_cols, onehot.categories_, strict=True):
            for _ in categories:
                mapping[idx] = col
                idx += 1
    return mapping
