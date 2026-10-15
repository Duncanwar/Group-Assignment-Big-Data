# Smart Energy Grid Analytics - Assignment I

AUCA MSc Advanced Big Data Analytics. 4,000 smart meters, 1-28 Sep 2026, 15-minute readings
(10,752,000 planned). Ingestion over MQTT/CSV, TimescaleDB storage experiments, continuous
aggregates, Grafana dashboards, and an hourly regional forecast.

`smart_meter_simulator.py` is the supplied generator and is submitted **unchanged**.

## Environment used (recorded)

| Item | Value |
|---|---|
| OS | Windows 11 Pro, build 26200 |
| CPU / RAM / storage | Intel Core Ultra 9 185H (16 cores, 22 logical) / 31.5 GB / KIOXIA BG6 1 TB NVMe |
| Python | 3.13.6 |
| PostgreSQL | 18.6, native on Windows (not a container or VM) |
| TimescaleDB | 2.29.2 Community |
| EMQX | 6.3.1, running in WSL2 |
| Grafana | 13.2 (OSS), http://localhost:3000 |
| Browser for 7.4 | Google Chrome 155.0.8059.40 driven by Playwright |
| PostgreSQL settings | shared_buffers 8,053 MB; work_mem 11,713 kB; max_parallel_workers_per_gather 11; jit off |
| Database / time zone | `smart_meters`; Africa/Kigali (all times CAT, +02:00) |

## Setup

```powershell
python -m pip install -r requirements.txt
# Secrets are never stored in code. Set them in each PowerShell window:
$env:DB_PASSWORD   = "<your PostgreSQL password>"
$env:MQTT_USER     = "<your EMQX user>"
$env:MQTT_PASSWORD = "<your EMQX password>"
# Optional overrides (defaults are in db_config.py): DB_HOST, DB_PORT, DB_NAME, DB_USER
```

Create the database once (skip if it exists):
```powershell
psql -U postgres -c "CREATE DATABASE smart_meters;"
psql -U postgres -c "ALTER DATABASE smart_meters SET timezone TO 'Africa/Kigali';"
psql -U postgres -d smart_meters -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```
Always pass `-d smart_meters` to `psql`; the default database is `postgres`.

## Execution order

Run everything from the project folder. SQL files are run with
`psql -U postgres -d smart_meters -a -f <file>`.

| Step | Task | Command |
|---|---|---|
| 1 | 1.2 tables | `sql\01_create_tables.sql` |
| 2 | 1.2 meters (4,000 rows) | `python load_meters.py` |
| 3 | 1.3 pilot (see below) | `python pilot_subscriber.py`, then `python pilot_publisher.py`; `python analyse_losses.py` if counts differ |
| 4 | 2.1 capture and load | `python capture_to_csv.py`, then `python load_csv.py` |
| 5 | 2.2 quality, 2.3 cleaning | `sql\02_data_quality.sql`, then `sql\03_clean_duplicates.sql` |
| 6 | 3.1 chunk tables, checks | `sql\04_chunk_tables.sql`, then `sql\05_verify_chunk_tables.sql` |
| 7 | 3.2 benchmark and plan | `python benchmark.py --label chunks --tables energy_readings energy_readings_3h energy_readings_week`, `sql\06_explain_q1.sql` |
| 8 | 4.1 compressed tables | `sql\07_compressed_tables.sql`, then `python compress_load.py` (no arguments) |
| 9 | 4.2 storage, 4.3 benchmark | `sql\08_compression_report.sql`, `python benchmark.py --label all --tables energy_readings energy_readings_3h energy_readings_week energy_time_compressed energy_meter_compressed`, `python improvement.py`, `sql\09_explain_q4_compressed.sql` |
| 10 | 4.4 facts | `python section4_facts.py` (no arguments) |
| 11 | 5.1-5.3 | `python section5_analysis.py` |
| 12 | 5.4 anomalies | `python section5_4_anomaly.py` |
| 13 | 6.1 aggregates | `sql\6_1a_create_caggs.sql`, `sql\6_1b_refresh_and_sizes.sql`, `sql\6_1c_policies.sql`, `sql\6_1_checks.sql` |
| 14 | 6.2 freshness test | `sql\6_2_freshness.sql` |
| 15 | 7.1-7.2 dashboards | `python section7_dashboards.py build`, then import `dashboards\Raw.json` and `dashboards\Aggregate.json` in Grafana (PostgreSQL data source `smart_meters` set as default) |
| 16 | 7.3 matching | `python section7_dashboards.py verify` |
| 17 | 7.4 timing | `sql\7_4_pause_jobs.sql`, then `python section7_4_timing.py` (needs `GRAFANA_USER`, `GRAFANA_PASSWORD`), then `sql\7_4_resume_jobs.sql` |
| 18 | 8 forecast | `python section8_forecast.py` |

Do not re-run `6_1a_create_caggs.sql` or `6_2_freshness.sql` casually: both drop and recreate objects.
Measured outputs (benchmark timings, validation table, panel comparisons) are in `results\`.

## Regenerating the full dataset (kept local, not in Git)

The generated data is in memory only and identical for every run.
```powershell
python capture_to_csv.py     # writes data\readings.csv and data\capture_stats.json (10,696,848 rows)
python load_csv.py           # bulk-loads into the empty energy_readings table
```
Then run steps 5 onward (cleaning leaves 10,643,735 unique rows).

## Pilot run and the four counts (1.3)

1. Start EMQX in WSL **[CONFIRM: add the command you use]** and check port 1883 answers on 127.0.0.1.
2. Empty the pilot table: `psql -U postgres -d smart_meters -c "TRUNCATE energy_live;"`
3. Terminal A (start first): `python pilot_subscriber.py`
4. Terminal B: `python pilot_publisher.py`
5. After the subscriber stops (it ends after about 15 seconds without messages):
   `psql -U postgres -d smart_meters -c "SELECT count(*) FROM energy_live;"`

Expected: 2,000 dictionaries taken from the generator, 2,000 messages acknowledged by the broker,
2,000 messages received by the subscriber, and 2,000 rows in `energy_live`.

## Repository layout

- `smart_meter_simulator.py` - supplied generator (unchanged)
- `db_config.py`, `mqtt_config.py` - connection settings (secrets come from environment variables)
- `load_meters.py`, `pilot_*.py`, `analyse_losses.py`, `capture_to_csv.py`, `load_csv.py` - ingestion
- `benchmark.py`, `compress_load.py`, `improvement.py`, `section4_facts.py` - Sections 3 and 4
- `section5_analysis.py`, `section5_4_anomaly.py` - Section 5
- `sql\` - all SQL (numbered files for Sections 1-4; `6_*` and `7_4_*` for Sections 6-7)
- `section7_dashboards.py`, `section7_4_timing.py`, `dashboards\` - Section 7 (panel SQL is in `section7_dashboards.py` and in the dashboard JSON)
- `section8_forecast.py` - Section 8
- `results\` - recorded timings, validation comparison, charts, panel comparison CSVs

## TimescaleDB 2.29 notes

- `timescaledb_information.continuous_aggregates` has no `finalized` column.
- Match refresh-policy jobs to views through `config->>'mat_hypertable_id'`, not `hypertable_name`.

## Group

| Name | Student ID | Contribution |
|---|---|---|
| ERIC BYIRINGIRO | 101389 | `<contribution>` |
| SANDRINE MFURANZIMA | 101411 | `<contribution>` |
| NDANYUZWE DUNCAN | 101413 | `<contribution>` |
