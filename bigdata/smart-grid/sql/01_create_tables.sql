-- 01_create_tables.sql
-- Creates the three tables for Assignment I. Run inside database smart_meters.

-- Live notepad: a regular PostgreSQL table where the MQTT subscriber stores pilot messages.
-- No primary key: duplicate readings must be allowed at this stage.
CREATE TABLE energy_live (
    meter_id      BIGINT,            -- ten-digit meter number (starts at 1000000000)
    event_time    TIMESTAMPTZ,       -- start of the 15-minute interval
    received_time TIMESTAMPTZ,       -- simulated arrival time (not the DB insertion time)
    power_kw      DOUBLE PRECISION,  -- average power over the interval (kW)
    voltage_v     DOUBLE PRECISION,  -- voltage (V)
    current_a     DOUBLE PRECISION,  -- current (A), computed with power factor 0.95
    frequency_hz  DOUBLE PRECISION,  -- grid frequency (Hz)
    energy_kwh    DOUBLE PRECISION   -- energy used in the interval (kWh) = power_kw * 0.25
);

-- Filing cabinet: same eight columns; it becomes a hypertable in the next statement.
CREATE TABLE energy_readings (
    meter_id      BIGINT,
    event_time    TIMESTAMPTZ NOT NULL,   -- partitioning column; TimescaleDB requires NOT NULL here
    received_time TIMESTAMPTZ,
    power_kw      DOUBLE PRECISION,
    voltage_v     DOUBLE PRECISION,
    current_a     DOUBLE PRECISION,
    frequency_hz  DOUBLE PRECISION,
    energy_kwh    DOUBLE PRECISION
);

-- Turn the table into a hypertable: partitioned by event_time, one chunk per day.
SELECT create_hypertable(
    'energy_readings',
    by_range('event_time', INTERVAL '1 day')
);

-- Address book: one row per meter, with a primary key on meter_id.
CREATE TABLE meters (
    meter_id       BIGINT PRIMARY KEY,   -- ten-digit meter number
    region         TEXT,                 -- 'Region 1' ... 'Region 10'
    customer_type  TEXT,                 -- residential, commercial or industrial
    base_power_kw  DOUBLE PRECISION,     -- the meter's typical power level (kW)
    power_factor   DOUBLE PRECISION      -- unitless; 0.95 for every meter
);