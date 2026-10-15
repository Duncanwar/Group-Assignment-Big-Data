-- 09_explain_q4_compressed.sql
-- Task 4.3.3: actual execution plans (timing and buffers) for Q4 on both compressed tables.
\set ECHO queries

EXPLAIN (ANALYZE, BUFFERS)
SELECT sum(energy_kwh), avg(power_kw), max(power_kw)
FROM energy_time_compressed
WHERE meter_id = 1000000000
  AND event_time >= '2026-09-22 00:00:00+02' AND event_time < '2026-09-29 00:00:00+02';

EXPLAIN (ANALYZE, BUFFERS)
SELECT sum(energy_kwh), avg(power_kw), max(power_kw)
FROM energy_meter_compressed
WHERE meter_id = 1000000000
  AND event_time >= '2026-09-22 00:00:00+02' AND event_time < '2026-09-29 00:00:00+02';