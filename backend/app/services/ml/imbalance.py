"""Shared class-imbalance detection, used two places for two different
reasons: a fast pre-flight check in the models router (from the dataset's
already-computed profile, before spending any training compute) and the
authoritative check in train.py (from the real y_train counts, always
exact). Both share this one threshold so the two checks never disagree
about what counts as "imbalanced"."""

IMBALANCE_THRESHOLD = 0.2


def minority_rate(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 1.0
    return min(counts.values()) / total


def is_imbalanced(rate: float) -> bool:
    return rate < IMBALANCE_THRESHOLD
