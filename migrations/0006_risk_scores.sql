-- 0006_risk_scores.sql
-- Combines a two-stage ("hurdle") model pair -- a classification model
-- predicting whether an entity has a positive outcome, and a regression
-- model predicting the magnitude when it does -- into one derived risk
-- score: P(positive_label) * predicted_magnitude. Scores are computed on
-- demand at read time from each model's current active_candidate; this
-- table only records which two models to combine. Additive, no breaking
-- changes to tables from 0001-0005.

create table risk_scores (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  name text not null,
  probability_model_id uuid not null references models(id),
  magnitude_model_id uuid not null references models(id),
  positive_label text not null default 'True',
  created_at timestamptz not null default now()
);
create index idx_risk_scores_org on risk_scores(organization_id);
