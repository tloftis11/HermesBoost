"""Prompt construction for LLM tasks: dataset description and intent chat.

Only profiling statistics (never full data / raw rows beyond a small capped
sample) are ever sent to the LLM. This is a hard design-doc requirement, not
just a style choice: it keeps a single LLM call's cost bounded regardless of
dataset size.
"""

import json

DATASET_DESCRIPTION_SYSTEM_PROMPT = (
    "You are HermesBoost, an assistant that writes short, plain-English "
    "descriptions of tabular datasets for domain experts who are not data "
    "scientists. Given column statistics and a small sample of rows, write "
    "a 3-5 sentence description covering what the dataset appears to "
    "contain, notable data-quality issues (nulls, skew), and any pattern "
    "worth flagging before modeling. Do not invent columns or values that "
    "are not present in the given statistics."
)

MAX_SAMPLE_ROWS = 10


def build_dataset_description_prompt(profile: dict, sample_rows: list[dict]) -> str:
    capped_sample = sample_rows[:MAX_SAMPLE_ROWS]
    payload = {
        "row_count": profile["row_count"],
        "column_count": profile["column_count"],
        "columns": profile["columns"],
        "sample_rows": capped_sample,
    }
    return (
        "Dataset statistics and a small sample (never the full data):\n\n"
        f"{json.dumps(payload, default=str, indent=2)}\n\n"
        "Write the description now."
    )


def build_intent_chat_system_prompt(dataset_name: str, columns: list[dict]) -> str:
    """System prompt for the intent-chat task.

    `columns` is the dataset's profiled column list (name + dtype + null
    rate, etc. -- from dataset_profiles.columns): the model must only ever
    propose `candidate_features` from these real column names, never invent
    one. It must also re-emit the FULL current modeling spec every turn once
    one exists (carrying forward unchanged fields), since the caller
    overwrites the stored spec with whatever comes back rather than merging
    a diff.
    """
    column_summary = [{"name": c["name"], "dtype": c["dtype"]} for c in columns]
    return (
        "You are HermesBoost's intent-parsing assistant. A domain expert -- "
        "not a data scientist -- is describing what they want to do with a "
        f"dataset called '{dataset_name}'. Its actual columns are:\n\n"
        f"{json.dumps(column_summary, indent=2)}\n\n"
        "Your job: hold a short, plain-English conversation, and once you "
        "understand enough, propose a modeling spec (task_type, "
        "task_description, target, candidate_features, evaluation_metric, "
        "retrain_cadence, score_cadence). Rules:\n"
        "- candidate_features must only ever be drawn from the real column "
        "names listed above -- never invent one.\n"
        "- Once a spec exists, every later turn must re-emit the FULL "
        "current spec (not just what changed) -- carry forward every field "
        "the user's latest message didn't ask you to change.\n"
        "- Leave modeling_spec null only on the very first turn or two, "
        "before there's enough to propose anything concrete.\n"
        "- Keep reply_message short (1-3 sentences) and conversational -- "
        "point the user at the spec panel rather than restating it in "
        "prose."
    )
