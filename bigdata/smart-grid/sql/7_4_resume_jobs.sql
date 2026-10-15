-- 7.4: resume assignment background jobs after the timing is finished
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';
SELECT now() AS cat_clock;

SELECT job_id, alter_job(job_id, scheduled => true) IS NOT NULL AS resumed
FROM timescaledb_information.jobs
WHERE proc_name IN ('policy_refresh_continuous_aggregate', 'policy_compression')
ORDER BY job_id;

\echo '--- jobs AFTER RESUME (scheduled must be t) ---'
SELECT job_id, proc_name, hypertable_name, scheduled, next_start
FROM timescaledb_information.jobs
WHERE proc_name IN ('policy_refresh_continuous_aggregate', 'policy_compression')
ORDER BY job_id;
