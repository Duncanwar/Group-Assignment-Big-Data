-- 6.1 / 6.2 evidence checks (read-only). Safe to run repeatedly; does NOT drop anything.
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';
SELECT current_database() AS db, now() AS cat_clock;

\echo '--- real-time aggregation disabled + original view definitions ---'
SELECT view_name, materialized_only
FROM timescaledb_information.continuous_aggregates
WHERE view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter','fresh_test_hourly')
ORDER BY view_name;

\x on
SELECT view_name, view_definition
FROM timescaledb_information.continuous_aggregates
WHERE view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter')
ORDER BY view_name;
\x off

\echo '--- refresh policy settings per view (fresh_test_hourly must show NO job) ---'
SELECT c.view_name, j.job_id, j.schedule_interval,
       j.config->>'start_offset' AS start_offset,
       j.config->>'end_offset'   AS end_offset,
       j.scheduled, j.next_start
FROM timescaledb_information.continuous_aggregates c
LEFT JOIN timescaledb_information.jobs j
  ON j.proc_name = 'policy_refresh_continuous_aggregate'
 AND j.config->>'mat_hypertable_id' =
     regexp_replace(c.materialization_hypertable_name, '^_materialized_hypertable_', '')
WHERE c.view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter','fresh_test_hourly')
ORDER BY c.view_name;

\echo '--- background job status (empty until each job has run once; re-run in ~15 min) ---'
SELECT s.job_id, c.view_name, s.last_run_status, s.last_run_started_at,
       s.last_successful_finish, s.next_start, s.total_runs, s.total_successes, s.total_failures
FROM timescaledb_information.job_stats s
JOIN timescaledb_information.continuous_aggregates c
  ON s.hypertable_name = c.materialization_hypertable_name
WHERE c.view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter')
ORDER BY c.view_name;
