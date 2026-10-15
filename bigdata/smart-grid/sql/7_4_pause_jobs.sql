-- 7.4: pause assignment background jobs (cagg refresh + compression policies) before timing
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';
SELECT current_database() AS db, now() AS cat_clock;

\echo '--- jobs BEFORE ---'
SELECT job_id, proc_name, hypertable_name, scheduled, next_start
FROM timescaledb_information.jobs
WHERE proc_name IN ('policy_refresh_continuous_aggregate', 'policy_compression')
ORDER BY job_id;

SELECT job_id, alter_job(job_id, scheduled => false) IS NOT NULL AS paused
FROM timescaledb_information.jobs
WHERE proc_name IN ('policy_refresh_continuous_aggregate', 'policy_compression')
ORDER BY job_id;

\echo '--- jobs AFTER (scheduled must be f) ---'
SELECT job_id, proc_name, hypertable_name, scheduled
FROM timescaledb_information.jobs
WHERE proc_name IN ('policy_refresh_continuous_aggregate', 'policy_compression')
ORDER BY job_id;

\echo '--- other active database sessions (should be none besides this one) ---'
SELECT pid, state, left(query, 70) AS query
FROM pg_stat_activity
WHERE datname = 'smart_meters' AND pid <> pg_backend_pid() AND state <> 'idle';
