-- 07_compressed_tables.sql
-- Task 4.1: two empty hypertables with the 1-day chunk interval chosen in Section 3,
-- columnstore settings, and compression policies that are created and then PAUSED.
\timing on
\set ECHO queries

-- 1. Same eight columns as energy_readings, then hypertables with 1-day chunks.
CREATE TABLE energy_time_compressed  (LIKE energy_readings);
CREATE TABLE energy_meter_compressed (LIKE energy_readings);
SELECT create_hypertable('energy_time_compressed',  by_range('event_time', INTERVAL '1 day'),
                         create_default_indexes => false);
SELECT create_hypertable('energy_meter_compressed', by_range('event_time', INTERVAL '1 day'),
                         create_default_indexes => false);

-- 2. Matching indexes (the same two as energy_readings).
CREATE INDEX energy_time_compressed_event_time_idx  ON energy_time_compressed  (event_time DESC);
CREATE INDEX energy_time_compressed_meter_time_idx  ON energy_time_compressed  (meter_id, event_time);
CREATE INDEX energy_meter_compressed_event_time_idx ON energy_meter_compressed (event_time DESC);
CREATE INDEX energy_meter_compressed_meter_time_idx ON energy_meter_compressed (meter_id, event_time);

-- 3a. energy_time_compressed: order by event_time DESC, NO segmentation.
--     An empty segmentby is tried first (it switches off any automatic choice); if this version
--     rejects it, the fallback leaves segmentby unset, which also means no segmentation.
DO $$
BEGIN
    BEGIN
        ALTER TABLE energy_time_compressed SET (
            timescaledb.enable_columnstore = true,
            timescaledb.orderby = 'event_time DESC',
            timescaledb.segmentby = '');
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'empty segmentby rejected (%): using the default, no segmentation', SQLERRM;
        ALTER TABLE energy_time_compressed SET (
            timescaledb.enable_columnstore = true,
            timescaledb.orderby = 'event_time DESC');
    END;
END $$;

-- 3b. energy_meter_compressed: the same ordering, segmented by meter_id.
ALTER TABLE energy_meter_compressed SET (
    timescaledb.enable_columnstore = true,
    timescaledb.orderby = 'event_time DESC',
    timescaledb.segmentby = 'meter_id');

-- 4. Policies: compress chunks whose END is more than 48 hours old.
CALL add_columnstore_policy('energy_time_compressed',  after => INTERVAL '48 hours');
CALL add_columnstore_policy('energy_meter_compressed', after => INTERVAL '48 hours');

-- 5. Pause both policies until the 4.3 measurements are complete.
SELECT alter_job(job_id, scheduled => false)
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_compression'
  AND hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed');

-- 6. Show the evidence: settings and policy status.
SELECT hypertable, segmentby, orderby
FROM timescaledb_information.hypertable_columnstore_settings
WHERE hypertable::text IN ('energy_time_compressed', 'energy_meter_compressed')
ORDER BY hypertable::text;

SELECT job_id, hypertable_name, proc_name, scheduled, schedule_interval, config
FROM timescaledb_information.jobs
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
ORDER BY hypertable_name;