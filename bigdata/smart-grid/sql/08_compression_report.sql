-- 08_compression_report.sql
-- Tasks 4.1.6 and 4.2: compressed-chunk lists, storage statistics and the five-table data checks.
\timing on
\set ECHO queries

-- A. Compressed chunks per table.
SELECT hypertable_name, count(*) AS total_chunks,
       count(*) FILTER (WHERE is_compressed) AS compressed_chunks
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('energy_readings', 'energy_time_compressed', 'energy_meter_compressed')
GROUP BY hypertable_name ORDER BY hypertable_name;

-- Are the SAME chunk ranges compressed in both new tables?
SELECT count(*) AS chunk_pairs,
       bool_and(a.is_compressed = b.is_compressed) AS same_ranges_compressed
FROM timescaledb_information.chunks a
JOIN timescaledb_information.chunks b
  ON a.range_start = b.range_start AND a.range_end = b.range_end
WHERE a.hypertable_name = 'energy_time_compressed' AND b.hypertable_name = 'energy_meter_compressed';

-- The compressed-chunk list itself, side by side.
SELECT a.range_start, a.range_end,
       a.is_compressed AS time_table_compressed, b.is_compressed AS meter_table_compressed
FROM timescaledb_information.chunks a
JOIN timescaledb_information.chunks b
  ON a.range_start = b.range_start AND a.range_end = b.range_end
WHERE a.hypertable_name = 'energy_time_compressed' AND b.hypertable_name = 'energy_meter_compressed'
ORDER BY a.range_start;

-- B. Sizes, compression ratio and percentage saved (baseline = uncompressed daily table).
--    Data = heap + toast. All chunks and their indexes are included.
WITH s AS (
    SELECT v.t AS tbl, d.table_bytes, d.index_bytes, d.toast_bytes, d.total_bytes
    FROM (VALUES ('energy_readings'), ('energy_time_compressed'), ('energy_meter_compressed')) v(t)
    CROSS JOIN LATERAL hypertable_detailed_size(v.t::regclass) d
)
SELECT s.tbl,
       round(s.table_bytes / 1048576.0, 1)  AS heap_mb,
       round(s.toast_bytes / 1048576.0, 1)  AS toast_mb,
       round(s.index_bytes / 1048576.0, 1)  AS index_mb,
       round(s.total_bytes / 1048576.0, 1)  AS total_mb,
       round(b.base_total::numeric / s.total_bytes, 2)                  AS compression_ratio,
       round(100.0 * (b.base_total - s.total_bytes) / b.base_total, 1)  AS pct_saved
FROM s CROSS JOIN (SELECT total_bytes AS base_total FROM s WHERE tbl = 'energy_readings') b
ORDER BY s.tbl;

-- C. Rows held in compressed chunks, using the ORIGINAL row counts from the uncompressed table.
SELECT c.hypertable_name, count(*) AS compressed_chunks,
       sum(x.n) AS rows_in_compressed_chunks,
       round(100.0 * sum(x.n) / 10643735, 2) AS pct_rows_in_compressed_chunks
FROM timescaledb_information.chunks c
CROSS JOIN LATERAL (SELECT count(*) AS n FROM energy_readings e
                    WHERE e.event_time >= c.range_start AND e.event_time < c.range_end) x
WHERE c.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed') AND c.is_compressed
GROUP BY c.hypertable_name ORDER BY c.hypertable_name;

-- D. The 3.1 data checks, now for all five tables.
\x on
WITH s AS (
    SELECT 'energy_readings'::text AS tbl, count(*) AS n_rows, count(DISTINCT meter_id) AS meters,
           min(event_time) AS earliest, max(event_time) AS latest,
           sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh FROM energy_readings
    UNION ALL SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id), min(event_time),
           max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_readings_3h
    UNION ALL SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id), min(event_time),
           max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_readings_week
    UNION ALL SELECT 'energy_time_compressed', count(*), count(DISTINCT meter_id), min(event_time),
           max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_time_compressed
    UNION ALL SELECT 'energy_meter_compressed', count(*), count(DISTINCT meter_id), min(event_time),
           max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_meter_compressed
)
SELECT s.tbl, s.n_rows, s.meters, s.earliest, s.latest, s.sum_power_kw, s.sum_energy_kwh,
       abs(s.sum_power_kw   - d.sum_power_kw)   AS diff_power_vs_daily,
       abs(s.sum_energy_kwh - d.sum_energy_kwh) AS diff_energy_vs_daily,
       (s.n_rows = 10643735 AND s.meters = 4000
        AND s.earliest = d.earliest AND s.latest = d.latest
        AND abs(s.sum_power_kw   - d.sum_power_kw)   <= 0.001
        AND abs(s.sum_energy_kwh - d.sum_energy_kwh) <= 0.001) AS all_checks_pass
FROM s CROSS JOIN (SELECT * FROM s WHERE tbl = 'energy_readings') d
ORDER BY s.tbl;
\x off