-- 0010_model_name.sql
-- Lets a model be named and addressed by that name instead of only its
-- UUID, for external API consumers. Nullable -- every existing model was
-- created without one; only UUID lookup works until someone names it.
-- Additive, no breaking changes to tables from 0001-0009.

alter table models add column name text;
