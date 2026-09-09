-- 0007_entity_id_column.sql
-- Panel-aware entity IDs for scoring. A spec's entity identifier (e.g. a
-- FIPS code in a county-year panel) can legitimately repeat across rows,
-- so it never gets profiled as dtype "id" (which requires row-level
-- uniqueness) and scoring silently falls back to a meaningless positional
-- index. This column lets a spec name that column explicitly, decoupled
-- from the profiler's guess. Nullable and additive -- unset behaves
-- exactly as before. Additive, no breaking changes to tables from 0001-0006.

alter table modeling_specs add column entity_id_column text;
