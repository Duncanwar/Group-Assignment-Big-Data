-- 05_verify_chunk_tables.sql
-- Task 3.1.3 and 3.1.4: prove the three tables hold identical data, then show chunks and indexes.
\timing on
\set ECHO queries
\x on

-- A. Data checks: every table must have 10,643,735 rows, 4,000 meters, identical dates,
--    and sums within 0.001 of the daily table (allowing floating-point rounding).
WITH s AS (
    SELECT 'energy_readings'::text AS tbl, count(*) AS n_rows, count(DISTINCT meter_id) AS meters,
           min(event_time) AS earliest, max(event_time) AS latest,
           sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh
    FROM energy_readings
    UNION ALL
    SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id), min(event_time), max(event_time),
           sum(power_kw), sum(energy_kwh)
    FROM energy_readings_3h
    UNION ALL
    SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id), min(event_time), max(event_time),
           sum(power_kw), sum(energy_kwh)
    FROM energy_readings_week
)
SELECT s.tbl, s.n_rows, s.meters, s.earliest, s.latest, s.sum_power_kw, s.sum_energy_kwh,
       abs(s.sum_power_kw   - d.sum_power_kw)   AS diff_power_vs_daily,
       abs(s.sum_energy_kwh - d.sum_energy_kwh) AS diff_energy_vs_daily,
       (s.n_rows = 10643735 AND s.meters = 4000
        AND s.earliest = d.earliest AND s.latest = d.latest
        AND abs(s.sum_power_kw   - d.sum_power_kw)   <= 0.001
        AND abs(s.sum_energy_kwh - d.sum_energy_kwh) <= 0.001) AS all_checks_pass
FROM s
CROSS JOIN (SELECT * FROM s WHERE tbl = 'energy_readings') d
ORDER BY s.tbl;

\x off

-- B. Chunk interval, chunk count and the date range the chunks cover.
SELECT h.hypertable_name, d.time_interval,
       (SELECT count(*) FROM timescaledb_information.chunks c
         WHERE c.hypertable_name = h.hypertable_name) AS chunks,
       (SELECT min(range_start) FROM timescaledb_information.chunks c
         WHERE c.hypertable_name = h.hypertable_name) AS first_chunk_start,
       (SELECT max(range_end) FROM timescaledb_information.chunks c
         WHERE c.hypertable_name = h.hypertable_name) AS last_chunk_end
FROM timescaledb_information.hypertables h
JOIN timescaledb_information.dimensions d USING (hypertable_schema, hypertable_name)
WHERE h.hypertable_name IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY h.hypertable_name;

-- C. Indexes: method and sort order must match across the three tables.
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY tablename, indexname;