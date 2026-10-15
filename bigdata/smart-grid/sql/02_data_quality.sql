-- 02_data_quality.sql
-- Task 2.2: data-quality diagnostics on energy_readings (read-only; nothing is changed).
\timing on
\set ECHO queries

-- A. One pass over the table: store five headline numbers in a temporary table.
--    A "unique reading" is one (meter_id, event_time) pair.
CREATE TEMP TABLE dq AS
WITH pairs AS (
    SELECT meter_id, event_time,
           count(*) AS copies,
           bool_or(received_time > event_time + interval '15 minutes') AS is_delayed
    FROM energy_readings
    GROUP BY meter_id, event_time
)
SELECT (SELECT count(*) FROM meters) * 28 * 96      AS planned,
       sum(copies)::bigint                          AS emitted,
       count(*)::bigint                             AS uniq,
       sum(copies - 1)::bigint                      AS extra,
       (count(*) FILTER (WHERE is_delayed))::bigint AS delayed
FROM pairs;

-- B. Measured counts against the assignment's reference table.
SELECT metric, measured, expected, measured = expected AS matches
FROM (
    SELECT 'planned_readings' AS metric, planned AS measured, 10752000::bigint AS expected FROM dq
    UNION ALL SELECT 'emitted_readings',   emitted,        10696848 FROM dq
    UNION ALL SELECT 'unique_readings',    uniq,           10643735 FROM dq
    UNION ALL SELECT 'duplicate_readings', extra,          53113    FROM dq
    UNION ALL SELECT 'delayed_unique',     delayed,        213090   FROM dq
    UNION ALL SELECT 'missing_readings',   planned - uniq, 108265   FROM dq
) r;

-- The two consistency checks required by 2.2.3.
SELECT uniq + extra = emitted    AS unique_plus_extra_equals_emitted,
       planned - uniq = 108265   AS planned_minus_unique_equals_missing
FROM dq;

-- C. The four percentages.
SELECT round(100.0 * (planned - uniq) / planned, 4) AS missing_pct,
       round(100.0 * extra   / uniq, 4)             AS duplicate_pct,
       round(100.0 * delayed / uniq, 4)             AS delayed_pct,
       round(100.0 * uniq    / planned, 4)          AS completeness_pct
FROM dq;

-- D. The five meters with the most missing readings (each meter should have 28 x 96 = 2688).
SELECT meter_id, 2688 - count(DISTINCT event_time) AS missing_readings
FROM energy_readings
GROUP BY meter_id
ORDER BY missing_readings DESC, meter_id
LIMIT 5;