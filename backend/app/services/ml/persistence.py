"""joblib (de)serialization of a fitted candidate pipeline. Each candidate is
saved as one self-contained Pipeline([("preprocessor", ...), ("estimator",
...)]) -- pipeline.predict(raw_df[feature_columns]) reproduces both the
imputation/scaling/encoding and the prediction, so this is everything needed
to run inference later without retraining."""

import io

import joblib
from sklearn.pipeline import Pipeline


def save_model_artifact(pipeline: Pipeline) -> bytes:
    buf = io.BytesIO()
    joblib.dump(pipeline, buf)
    return buf.getvalue()


def load_model_artifact(data: bytes) -> Pipeline:
    return joblib.load(io.BytesIO(data))
