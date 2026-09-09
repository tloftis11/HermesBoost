# Migrations

Plain numbered SQL files, applied in order. No migration framework yet at this
scale -- just `.sql` files and a steady hand.

Current files: `0001_init.sql` (organizations, datasets, dataset_profiles,
llm_task_model_config, llm_usage_log), `0002_intent_chat.sql`
(modeling_specs, chat_messages). Apply both, in order, on a fresh database.

## Applying against Supabase

Either paste each file into the Supabase project's SQL editor in order, or
run them with `psql` against the project's connection string:

```bash
psql "$DATABASE_URL" -f migrations/0001_init.sql
psql "$DATABASE_URL" -f migrations/0002_intent_chat.sql
```

## Validating locally first

Before touching the real Supabase project, apply the same files to a
throwaway local Postgres to catch syntax errors for free:

```bash
docker run --rm -d --name hb-pg -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
psql "postgresql://postgres:postgres@localhost:5432/postgres" -f migrations/0001_init.sql
psql "postgresql://postgres:postgres@localhost:5432/postgres" -f migrations/0002_intent_chat.sql
docker stop hb-pg
```

(Docker wasn't available in the environment these were developed in, so this
exact validation hasn't been run yet -- worth doing once Docker or a real
Supabase project is at hand, before applying to production data.)
