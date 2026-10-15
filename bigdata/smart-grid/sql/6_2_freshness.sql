-- 6.2: freshness and delayed-arrival test on a separate hypertable
-- Run once, with no other workload. Times are relative to the actual test time.
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';

\echo '=== Setup: table, hypertable, hourly continuous aggregate (no data, real-time OFF, no policy) ==='
DROP MATERIALIZED VIEW IF EXISTS fresh_test_hourly;
DROP TABLE IF EXISTS fresh_test;
CREATE TABLE fresh_test (
    event_time TIMESTAMPTZ      NOT NULL,
    energy_kwh DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('fresh_test', by_range('event_time', INTERVAL '1 day'));

CREATE MATERIALIZED VIEW fresh_test_hourly
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(INTERVAL '1 hour', event_time, 'Africa/Kigali') AS bucket,
       sum(energy_kwh) AS sum_energy_kwh,
       count(*)        AS reading_count
FROM fresh_test
GROUP BY 1
WITH NO DATA;

\d+ fresh_test
\d+ fresh_test_hourly
SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates
WHERE view_name = 'fresh_test_hourly';
SELECT count(*) AS refresh_policies_on_test_view
FROM timescaledb_information.jobs j
JOIN timescaledb_information.continuous_aggregates c
  ON j.hypertable_name = c.materialization_hypertable_name
WHERE c.view_name = 'fresh_test_hourly';

\echo '=== Record test time, H (start of most recent completed CAT hour) and older hour (H - 48 h) ==='
SELECT now() AS test_time,
       date_trunc('hour', now()) - INTERVAL '1 hour' AS h,
       date_trunc('hour', now()) - INTERVAL '1 hour' - INTERVAL '48 hours' AS o \gset
SELECT :'o'::timestamptz + INTERVAL '10 minutes' AS e1,
       :'o'::timestamptz + INTERVAL '25 minutes' AS e2,
       :'h'::timestamptz + INTERVAL '10 minutes' AS e3 \gset
SELECT :'test_time'::timestamptz AS actual_test_time_cat,
       :'h'::timestamptz AS hour_h_start,
       :'o'::timestamptz AS older_hour_start,
       :'e1'::timestamptz AS insert1_1kwh_event_time,
       :'e2'::timestamptz AS insert2_0_5kwh_event_time,
       :'e3'::timestamptz AS insert3_2kwh_event_time;

\echo '=== Stage 1: insert 1 kWh into older hour, refresh ONLY that hour ==='
INSERT INTO fresh_test VALUES (:'e1', 1.0);
CALL refresh_continuous_aggregate('fresh_test_hourly', :'o'::timestamptz, :'o'::timestamptz + INTERVAL '1 hour');
SELECT now() AS cat_clock;
SELECT * FROM fresh_test_hourly ORDER BY bucket;

\echo '=== Stage 2: insert 0.5 kWh (older hour) and 2 kWh (hour H); BEFORE refresh, real-time OFF ==='
INSERT INTO fresh_test VALUES (:'e2', 0.5);
INSERT INTO fresh_test VALUES (:'e3', 2.0);
SELECT now() AS cat_clock;
\echo 'RAW table:'
SELECT time_bucket(INTERVAL '1 hour', event_time, 'Africa/Kigali') AS bucket,
       sum(energy_kwh) AS sum_energy_kwh, count(*) AS reading_count
FROM fresh_test GROUP BY 1 ORDER BY 1;
\echo 'AGGREGATE (materialized only):'
SELECT * FROM fresh_test_hourly ORDER BY bucket;

\echo '=== Stage 3: enable real-time aggregation, still BEFORE refresh ==='
ALTER MATERIALIZED VIEW fresh_test_hourly SET (timescaledb.materialized_only = false);
SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates
WHERE view_name = 'fresh_test_hourly';
\echo 'RAW table:'
SELECT time_bucket(INTERVAL '1 hour', event_time, 'Africa/Kigali') AS bucket,
       sum(energy_kwh) AS sum_energy_kwh, count(*) AS reading_count
FROM fresh_test GROUP BY 1 ORDER BY 1;
\echo 'AGGREGATE (real-time on):'
SELECT * FROM fresh_test_hourly ORDER BY bucket;

\echo '=== Stage 4: manually refresh both complete hours, then query again ==='
CALL refresh_continuous_aggregate('fresh_test_hourly', :'o'::timestamptz, :'h'::timestamptz + INTERVAL '1 hour');
SELECT now() AS cat_clock;
\echo 'RAW table (expect older hour 1.5 kWh / 2 rows, hour H 2 kWh / 1 row):'
SELECT time_bucket(INTERVAL '1 hour', event_time, 'Africa/Kigali') AS bucket,
       sum(energy_kwh) AS sum_energy_kwh, count(*) AS reading_count
FROM fresh_test GROUP BY 1 ORDER BY 1;
\echo 'AGGREGATE after refresh:'
SELECT * FROM fresh_test_hourly ORDER BY bucket;

\echo '=== Policy window of the 6.1 policies at the recorded test time: [T-3 days, T-1 hour) ==='
SELECT :'test_time'::timestamptz - INTERVAL '3 days' AS policy_window_start,
       :'test_time'::timestamptz - INTERVAL '1 hour' AS policy_window_end,
       :'o'::timestamptz AS older_hour_start,
       :'h'::timestamptz AS hour_h_start;
