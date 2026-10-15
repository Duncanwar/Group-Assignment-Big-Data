"""load_csv.py - Task 2.1: bulk-load data\\readings.csv into the empty energy_readings hypertable."""
import json
import os
import time
from datetime import datetime

import smart_meter_simulator as sim          # only used here to read the expected counts
from db_config import get_connection

CSV_PATH = os.path.join("data", "readings.csv")
CHUNK_BYTES = 16 * 1024 * 1024               # read the file in 16 MB pieces, never all at once

# COPY ... FROM STDIN lets Python stream the file into the server.
# HEADER true skips the first line (the column names).
COPY_SQL = """
    COPY energy_readings (meter_id, event_time, received_time, power_kw,
                          voltage_v, current_a, frequency_hz, energy_kwh)
    FROM STDIN WITH (FORMAT csv, HEADER true)
"""


def now_cat():
    # Local time with its +02:00 offset (CAT), recorded for the report.
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main():
    expected = sim.dataset_info()["expected_counts"]["emitted_readings"]
    total_bytes = os.path.getsize(CSV_PATH)

    conn = get_connection()
    # Task 2.1.2: energy_readings must be empty before loading.
    existing = conn.execute("SELECT count(*) FROM energy_readings").fetchone()[0]
    conn.commit()
    if existing != 0:
        print(f"STOP: energy_readings already holds {existing:,} rows. Empty it first.")
        return

    print(f"Load started (CAT) : {now_cat()}")
    started_cat = now_cat()
    sent = 0
    chunks = 0
    t0 = time.perf_counter()                 # load seconds are counted from the first database write

    with conn.cursor() as cur:
        with cur.copy(COPY_SQL) as copy:     # opens the COPY stream to the server
            with open(CSV_PATH, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_BYTES)
                    if not chunk:            # end of file
                        break
                    copy.write(chunk)        # send this piece to PostgreSQL
                    sent += len(chunk)
                    chunks += 1
                    if chunks % 8 == 0:      # a progress line about every 128 MB
                        print(f"  sent {sent / 1024**2:8.0f} MB  ({100 * sent / total_bytes:5.1f}%)"
                              f"  {time.perf_counter() - t0:7.1f} s")
    conn.commit()                            # the final commit ends the timed load
    load_seconds = time.perf_counter() - t0
    finished_cat = now_cat()

    # Counted AFTER the commit and outside the timed load.
    rows = conn.execute("SELECT count(*) FROM energy_readings").fetchone()[0]
    status = "MATCH" if rows == expected else "MISMATCH"
    print("---------------- LOAD SUMMARY ----------------")
    print(f"Started (CAT)                          : {started_cat}")
    print(f"Final commit (CAT)                     : {finished_cat}")
    print(f"Load seconds (first write to commit)   : {load_seconds:.1f}")
    print(f"Expected emitted_readings              : {expected:,}")
    print(f"Committed rows in energy_readings      : {rows:,}   -> {status}")

    with open(os.path.join("data", "load_stats.json"), "w", encoding="utf-8") as g:
        json.dump({"route": "CSV + COPY", "started_cat": started_cat, "finished_cat": finished_cat,
                   "load_seconds": round(load_seconds, 1), "committed_rows": rows,
                   "expected_emitted": expected}, g, indent=2)
    conn.close()


if __name__ == "__main__":
    main()