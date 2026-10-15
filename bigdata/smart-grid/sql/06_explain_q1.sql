-- 06_explain_q1.sql
-- Task 3.2.5: one execution plan with actual timing and buffer statistics per configuration (Q1).
\set ECHO queries

EXPLAIN (ANALYZE, BUFFERS)
SELECT date_trunc('hour', event_time) AS hour_cat, avg(power_kw) AS avg_power_kw
FROM energy_readings
WHERE event_time >= '2026-09-21 00:00:00+02' AND event_time < '2026-09-22 00:00:00+02'
GROUP BY 1 ORDER BY 1;

EXPLAIN (ANALYZE, BUFFERS)
SELECT date_trunc('hour', event_time) AS hour_cat, avg(power_kw) AS avg_power_kw
FROM energy_readings_3h
WHERE event_time >= '2026-09-21 00:00:00+02' AND event_time < '2026-09-22 00:00:00+02'
GROUP BY 1 ORDER BY 1;

EXPLAIN (ANALYZE, BUFFERS)
SELECT date_trunc('hour', event_time) AS hour_cat, avg(power_kw) AS avg_power_kw
FROM energy_readings_week
WHERE event_time >= '2026-09-21 00:00:00+02' AND event_time < '2026-09-22 00:00:00+02'
GROUP BY 1 ORDER BY 1;