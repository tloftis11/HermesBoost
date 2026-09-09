-- 0004_scoring.sql
-- HermesBoost milestone 5: scoring/inference. Additive, no breaking changes
-- to tables from 0001-0003.

-- Strictly append-only (design doc §4.6) -- one row per scored entity per
-- model per score run, never overwritten or upserted.
create table scheduled_scores (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  model_id uuid not null references models(id) on delete cascade,
  model_run_id uuid not null references model_runs(id) on delete cascade,
  model_candidate_id uuid not null references model_candidates(id),
  entity_id text not null,
  score_date date not null,
  predicted_value double precision,       -- regression only
  predicted_label text,                    -- classification only, decoded via label_classes
  predicted_probability double precision,  -- classification only, probability of predicted_label
  created_at timestamptz not null default now()
);
create index idx_scheduled_scores_model_date on scheduled_scores(model_id, score_date desc);
create index idx_scheduled_scores_entity on scheduled_scores(model_id, entity_id, score_date desc);
create index idx_scheduled_scores_run on scheduled_scores(model_run_id);
