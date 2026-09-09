"""One-off local dev helper: creates tables and seeds the default org +
model-routing row directly via SQLAlchemy, for developers running against a
local SQLite/Postgres instance without Supabase configured yet.

migrations/0001_init.sql remains the source of truth for the real Supabase
schema (Postgres-specific: pgcrypto, gen_random_uuid()) -- this script is a
SQLite/local-Postgres-friendly equivalent for offline dev only.

Usage:
    python -m scripts.dev_bootstrap
"""

import asyncio

from sqlalchemy import select

from app.db import Base, engine, async_session_maker
from app.models.llm_task_model_config import LlmTaskModelConfig
from app.models.organization import Organization


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as db:
        existing = await db.execute(select(Organization).where(Organization.slug == "default"))
        if existing.scalar_one_or_none() is None:
            db.add(Organization(name="Default Organization", slug="default"))

        existing_cfg = await db.execute(
            select(LlmTaskModelConfig).where(LlmTaskModelConfig.task_type == "dataset_description")
        )
        if existing_cfg.scalar_one_or_none() is None:
            db.add(LlmTaskModelConfig(task_type="dataset_description", model_id="claude-opus-5"))

        await db.commit()

    print("Dev DB bootstrapped: tables created, default org + model config seeded.")


if __name__ == "__main__":
    asyncio.run(main())
