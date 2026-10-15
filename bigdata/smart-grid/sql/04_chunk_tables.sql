-- 04_chunk_tables.sql
-- Task 3.1: build energy_readings_3h and energy_readings_week, copy the cleaned rows,
-- and give all three tables matching indexes. Run once, on an empty setup.
\timing on
\set ECHO queries

-- 1. Same eight columns as energy_readings (LIKE copies column names, types and NOT NULL).
CREATE TABLE energy_readings_3h   (LIKE energy_readings);
CREATE TABLE energy_readings_week (LIKE energy_readings);

-- 2. Turn them into hypertables partitioned by event_time.
--    create_default_indexes => false: we create every index ourselves so the three tables match exactly.
SELECT create_hypertable('energy_readings_3h',   by_range('event_time', INTERVAL '3 hours'),
                         create_default_indexes => false);
SELECT create_hypertable('energy_readings_week', by_range('event_time', INTERVAL '7 days'),
                         create_default_indexes => false);

-- 3. Copy the cleaned rows (10,643,735 each). Indexes come AFTER the load because it is faster.
INSERT INTO energy_readings_3h   SELECT * FROM energy_readings;
INSERT INTO energy_readings_week SELECT * FROM energy_readings;

-- 4. Matching non-unique B-tree indexes on all three tables:
--      (a) event_time, descending      (b) meter_id then event_time, ascending
--    energy_readings already has (a) from create_hypertable (energy_readings_event_time_idx).
CREATE INDEX energy_readings_3h_event_time_idx   ON energy_readings_3h   (event_time DESC);
CREATE INDEX energy_readings_week_event_time_idx ON energy_readings_week (event_time DESC);
CREATE INDEX energy_readings_meter_time_idx      ON energy_readings      (meter_id, event_time);
CREATE INDEX energy_readings_3h_meter_time_idx   ON energy_readings_3h   (meter_id, event_time);
CREATE INDEX energy_readings_week_meter_time_idx ON energy_readings_week (meter_id, event_time);

-- 5. Same housekeeping on all three so the planner has current statistics (needed before 3.2).
VACUUM (ANALYZE) energy_readings;
VACUUM (ANALYZE) energy_readings_3h;
VACUUM (ANALYZE) energy_readings_week;