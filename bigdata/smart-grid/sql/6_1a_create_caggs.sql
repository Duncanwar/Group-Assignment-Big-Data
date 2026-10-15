-- 6.1 (a): create three initially unpopulated continuous aggregates over energy_readings
\set ON_ERROR_STOP on
SET timezone = 'Africa/Kigali';
SELECT current_database() AS db, now() AS cat_clock;

DROP MATERIALIZED VIEW IF EXISTS cagg_15min_region;
DROP MATERIALIZED VIEW IF EXISTS cagg_hourly_region;
DROP MATERIALIZED VIEW IF EXISTS cagg_daily_meter;

-- 1) 15-minute bucket x region (inner join to meters)
CREATE MATERIALIZED VIEW cagg_15min_region
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '15 minutes', r.event_time) AS bucket,
       m.region,
       sum(r.energy_kwh) AS sum_energy_kwh,
       sum(r.power_kw)   AS sum_power_kw,
       count(*)          AS reading_count
FROM energy_readings r
JOIN meters m ON r.meter_id = m.meter_id
GROUP BY 1, 2
WITH NO DATA;

-- 2) CAT hour x region (inner join to meters)
CREATE MATERIALIZED VIEW cagg_hourly_region
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', r.event_time, 'Africa/Kigali') AS bucket,
       m.region,
       sum(r.energy_kwh) AS sum_energy_kwh,
       sum(r.power_kw)   AS sum_power_kw,
       count(*)          AS reading_count
FROM energy_readings r
JOIN meters m ON r.meter_id = m.meter_id
GROUP BY 1, 2
WITH NO DATA;

-- 3) CAT day x meter_id
CREATE MATERIALIZED VIEW cagg_daily_meter
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', r.event_time, 'Africa/Kigali') AS bucket,
       r.meter_id,
       sum(r.energy_kwh) AS sum_energy_kwh,
       sum(r.power_kw)   AS sum_power_kw,
       count(*)          AS reading_count
FROM energy_readings r
GROUP BY 1, 2
WITH NO DATA;

-- disable real-time aggregation on all three (stored aggregates only)
ALTER MATERIALIZED VIEW cagg_15min_region  SET (timescaledb.materialized_only = true);
ALTER MATERIALIZED VIEW cagg_hourly_region SET (timescaledb.materialized_only = true);
ALTER MATERIALIZED VIEW cagg_daily_meter   SET (timescaledb.materialized_only = true);

-- evidence: definitions and settings
\d+ cagg_15min_region
\d+ cagg_hourly_region
\d+ cagg_daily_meter

SELECT view_name, materialized_only, finalized
FROM timescaledb_information.continuous_aggregates
WHERE view_name IN ('cagg_15min_region','cagg_hourly_region','cagg_daily_meter')
ORDER BY view_name;

SELECT 'cagg_15min_region' AS view, count(*) AS rows_before_refresh FROM cagg_15min_region
UNION ALL SELECT 'cagg_hourly_region', count(*) FROM cagg_hourly_region
UNION ALL SELECT 'cagg_daily_meter',   count(*) FROM cagg_daily_meter;
