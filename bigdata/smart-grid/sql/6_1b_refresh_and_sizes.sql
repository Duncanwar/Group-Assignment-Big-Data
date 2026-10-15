-- 6.1 (b): manual initial refresh (timed), storage, sample rows, correctness checks
-- Run BEFORE any refresh policy is added. Pause other workloads while this runs.
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';
SELECT now() AS cat_clock_start;
\timing on

\echo '--- refresh cagg_15min_region (whole generated period) ---'
CALL refresh_continuous_aggregate('cagg_15min_region',  '2026-09-01 00:00:00+02', '2026-09-29 00:00:00+02');
\echo '--- refresh cagg_hourly_region ---'
CALL refresh_continuous_aggregate('cagg_hourly_region', '2026-09-01 00:00:00+02', '2026-09-29 00:00:00+02');
\echo '--- refresh cagg_daily_meter ---'
CALL refresh_continuous_aggregate('cagg_daily_meter',   '2026-09-01 00:00:00+02', '2026-09-29 00:00:00+02');

\timing off
SELECT now() AS cat_clock_end;
\echo 'Refresh duration = the "Time:" value above for each CALL (ms; divide by 1000 for seconds)'

\echo '--- materialized data + index size ---'
SELECT c.view_name,
       pg_size_pretty(d.table_bytes) AS data_size,
       pg_size_pretty(d.index_bytes) AS index_size,
       pg_size_pretty(d.total_bytes) AS total_size,
       d.table_bytes, d.index_bytes, d.total_bytes
FROM timescaledb_information.continuous_aggregates c
CROSS JOIN LATERAL hypertable_detailed_size(
     format('%I.%I', c.materialization_hypertable_schema,
                     c.materialization_hypertable_name)::regclass) d
WHERE c.view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter')
ORDER BY c.view_name;

\echo '--- row counts (expect ~26,880 / ~6,720 / ~112,000) ---'
SELECT 'cagg_15min_region' AS view, count(*) AS rows FROM cagg_15min_region
UNION ALL SELECT 'cagg_hourly_region', count(*) FROM cagg_hourly_region
UNION ALL SELECT 'cagg_daily_meter',   count(*) FROM cagg_daily_meter;

\echo '--- sample populated rows ---'
SELECT * FROM cagg_15min_region  ORDER BY bucket, region LIMIT 5;
SELECT * FROM cagg_hourly_region ORDER BY bucket, region LIMIT 5;
SELECT * FROM cagg_daily_meter   ORDER BY bucket, meter_id LIMIT 5;

\echo '--- correctness: reading_count and energy must match energy_readings ---'
SELECT 'energy_readings' AS source, count(*) AS readings, sum(energy_kwh) AS energy_kwh
FROM energy_readings
UNION ALL SELECT 'cagg_15min_region',  sum(reading_count), sum(sum_energy_kwh) FROM cagg_15min_region
UNION ALL SELECT 'cagg_hourly_region', sum(reading_count), sum(sum_energy_kwh) FROM cagg_hourly_region
UNION ALL SELECT 'cagg_daily_meter',   sum(reading_count), sum(sum_energy_kwh) FROM cagg_daily_meter;
