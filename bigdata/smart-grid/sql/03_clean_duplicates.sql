-- 03_clean_duplicates.sql
-- Task 2.3: remove exact duplicate copies from energy_readings. Safe to re-run.
\timing on
\set ECHO queries

-- 1. Snapshot BEFORE cleaning, kept in a temporary table for the final comparison.
CREATE TEMP TABLE before_clean AS
SELECT count(*) AS n_rows, sum(energy_kwh) AS kwh FROM energy_readings;
SELECT * FROM before_clean;

-- 2. Investigate: pairs that share (meter_id, event_time) but whose six values do NOT all match.
--    This should return 0. If not, those pairs are conflicts and will NOT be deleted below.
SELECT count(*) AS conflicting_pairs
FROM (
    SELECT meter_id, event_time
    FROM energy_readings
    GROUP BY meter_id, event_time
    HAVING count(*) > 1
       AND (count(DISTINCT received_time) > 1 OR count(DISTINCT power_kw)    > 1
         OR count(DISTINCT voltage_v)     > 1 OR count(DISTINCT current_a)   > 1
         OR count(DISTINCT frequency_hz)  > 1 OR count(DISTINCT energy_kwh)  > 1)
) c;

-- 3. Delete extra copies, chunk by chunk. Rows are grouped by ALL eight values, so only
--    fully identical copies are removed, and the first copy (lowest physical position) stays.
--    Duplicates share the same event_time, so both copies always sit in the same chunk.
DO $$
DECLARE
    c     regclass;          -- the chunk being cleaned
    n     bigint;            -- rows deleted in this chunk
    total bigint := 0;       -- rows deleted overall
BEGIN
    FOR c IN SELECT show_chunks('energy_readings') LOOP
        EXECUTE format($f$
            DELETE FROM %s
            WHERE ctid IN (
                SELECT ctid FROM (
                    SELECT ctid,
                           row_number() OVER (
                               PARTITION BY meter_id, event_time, received_time, power_kw,
                                            voltage_v, current_a, frequency_hz, energy_kwh
                               ORDER BY ctid) AS rn
                    FROM %s) s
                WHERE rn > 1)
        $f$, c, c);
        GET DIAGNOSTICS n = ROW_COUNT;
        total := total + n;
        RAISE NOTICE 'chunk % : deleted % duplicate rows', c, n;
    END LOOP;
    RAISE NOTICE 'TOTAL duplicate rows deleted: %', total;
END $$;

-- 4. Verify: before and after, rows and summed energy.
SELECT b.n_rows                  AS rows_before,
       a.n_rows                  AS rows_after,
       b.n_rows - a.n_rows       AS rows_removed,
       a.n_rows = 10643735       AS equals_expected_unique,
       b.kwh                     AS kwh_before,
       a.kwh                     AS kwh_after,
       b.kwh - a.kwh             AS kwh_removed
FROM before_clean b,
     (SELECT count(*) AS n_rows, sum(energy_kwh) AS kwh FROM energy_readings) a;

-- No (meter_id, event_time) pair may remain more than once.
SELECT count(*) AS duplicate_pairs_left
FROM (SELECT 1 FROM energy_readings GROUP BY meter_id, event_time HAVING count(*) > 1) d;

-- 5. Refresh statistics so the planner and later benchmarks see the cleaned table.
VACUUM (ANALYZE) energy_readings;