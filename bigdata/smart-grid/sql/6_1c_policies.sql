-- 6.1 (c): add refresh policies (3-day lookback, 1-hour end offset, 15-minute schedule)
-- Run only AFTER 6_1b measurements are complete.
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';
SELECT now() AS cat_clock;

SELECT add_continuous_aggregate_policy('cagg_15min_region',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
       schedule_interval => INTERVAL '15 minutes');
SELECT add_continuous_aggregate_policy('cagg_hourly_region',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
       schedule_interval => INTERVAL '15 minutes');
SELECT add_continuous_aggregate_policy('cagg_daily_meter',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
       schedule_interval => INTERVAL '15 minutes');

\echo '--- policy settings ---'
SELECT j.job_id, c.view_name, j.proc_name, j.schedule_interval, j.config, j.scheduled, j.next_start
FROM timescaledb_information.jobs j
JOIN timescaledb_information.continuous_aggregates c
  ON j.hypertable_name = c.materialization_hypertable_name
WHERE j.proc_name = 'policy_refresh_continuous_aggregate'
ORDER BY c.view_name;

\echo '--- background job status (re-run this part after a minute if runs are still empty) ---'
SELECT s.job_id, c.view_name, s.last_run_status, s.last_run_started_at,
       s.total_runs, s.total_successes, s.total_failures
FROM timescaledb_information.job_stats s
JOIN timescaledb_information.continuous_aggregates c
  ON s.hypertable_name = c.materialization_hypertable_name
WHERE c.view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter')
ORDER BY c.view_name;

\echo '--- policy window now: policies refresh [now-3 days, now-1 hour), so September data is NOT touched ---'
SELECT now() - INTERVAL '3 days' AS policy_window_start, now() - INTERVAL '1 hour' AS policy_window_end;
