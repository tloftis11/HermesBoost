"""Maps a modeling spec's user-facing task_type to the narrower ml_task this
milestone's training pipeline actually supports.

V1 scope: classification and regression only. time_series_forecast,
clustering, and anomaly_detection need fundamentally different data prep
(temporal splits, no labeled target, different metrics) and are deferred
outright rather than half-supported.
"""

from typing import Literal

MlTask = Literal["classification", "regression"]

_SUPPORTED = {
    "classification": "classification",
    "risk_scoring": "classification",
    "regression": "regression",
}


class UnsupportedTaskTypeError(Exception):
    def __init__(self, spec_task_type: str):
        self.spec_task_type = spec_task_type
        super().__init__(
            f"task_type '{spec_task_type}' is not supported for building models "
            "in this release. Only 'classification', 'risk_scoring', and "
            "'regression' can be built today."
        )


def to_ml_task(spec_task_type: str) -> MlTask:
    ml_task = _SUPPORTED.get(spec_task_type)
    if ml_task is None:
        raise UnsupportedTaskTypeError(spec_task_type)
    return ml_task
