"""One-off-per-invocation dispatcher: checks every confirmed modeling spec's
retrain_cadence/score_cadence against its model's run history and enqueues
a train_model or score_model task when due. Meant to be invoked by a Render
Cron Job on a fixed schedule (e.g. hourly) rather than run as a persistent
process -- see render.yaml's hermesboost-scheduler service.

Manual and scheduled runs are indistinguishable here on purpose: whichever
run last happened (however it was triggered) resets that cadence's clock,
so a manual "Retrain ->"/"Score now" click mid-cycle correctly pushes out
the next automatic one -- no run-origin tracking needed.

Usage:
    python -m scripts.dispatch_scheduled_runs
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import async_session_maker
from app.models.model import Model
from app.models.model_run import ModelRun
from app.models.modeling_spec import ModelingSpec
from app.tasks.score_model import score_model
from app.tasks.train_model import train_model

CADENCE_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}


async def main() -> None:
    dispatched = 0
    async with async_session_maker() as db:
        specs = (
            await db.execute(select(ModelingSpec).where(ModelingSpec.status == "confirmed"))
        ).scalars().all()
        now = datetime.now(timezone.utc)

        for spec in specs:
            model = (
                await db.execute(select(Model).where(Model.modeling_spec_id == spec.id))
            ).scalar_one_or_none()
            if model is None:
                continue  # never built -- the scheduler never builds for the first time

            if await _maybe_dispatch(db, model, spec.retrain_cadence, "train", train_model, now):
                dispatched += 1
            if model.status == "ready":  # only score a model that has something to score with
                if await _maybe_dispatch(db, model, spec.score_cadence, "score", score_model, now):
                    dispatched += 1

    print(f"dispatch_scheduled_runs: {dispatched} run(s) enqueued")


async def _maybe_dispatch(db, model: Model, cadence: str, run_type: str, task, now: datetime) -> bool:
    interval = CADENCE_INTERVALS[cadence]
    last_run = (
        await db.execute(
            select(ModelRun)
            .where(ModelRun.model_id == model.id, ModelRun.run_type == run_type)
            .order_by(ModelRun.started_at.desc())
        )
    ).scalars().first()

    if last_run is not None and last_run.status == "running":
        return False  # a run of this type is already in flight -- never overlap

    if last_run is None:
        # Unreachable for "train" (a Model row is only created by /build,
        # which creates the first train run in the same request) -- kept
        # defensive-only. Reachable for "score": a freshly-ready model with
        # no score run yet should score right away rather than wait a full
        # cadence period, so it doesn't look broken with zero scored rows.
        due = run_type == "score"
    else:
        started_at = last_run.started_at
        if started_at.tzinfo is None:
            # SQLite (used in tests/local dev) doesn't preserve tzinfo on a
            # DateTime(timezone=True) column even though the value stored
            # was always UTC -- reinterpret rather than compare naive vs.
            # aware and crash. Real Postgres/asyncpg already returns this
            # tz-aware, so this is a no-op there.
            started_at = started_at.replace(tzinfo=timezone.utc)
        due = now - started_at >= interval

    if not due:
        return False

    run = ModelRun(organization_id=model.organization_id, model_id=model.id, run_type=run_type, status="running")
    db.add(run)
    await db.flush()
    await db.commit()

    # .to_thread avoids the nested-event-loop crash under
    # CELERY_TASK_ALWAYS_EAGER (this script already runs inside its own
    # asyncio.run(), and eager .delay() calls asyncio.run() again
    # internally) -- same reasoning as datasets.py's/models.py's upload
    # and build endpoints. In production (eager mode off) .delay() just
    # enqueues onto Redis and returns immediately either way.
    await asyncio.to_thread(task.delay, run.id)
    return True


if __name__ == "__main__":
    asyncio.run(main())
