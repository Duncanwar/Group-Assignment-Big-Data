"""compress_load.py - Tasks 4.1.4 to 4.1.6.

Copies the cleaned data from energy_readings into the two compressed tables ONE CHUNK AT A TIME.
After a chunk is fully loaded it is compressed (moved to the columnstore) if the chunk's end is
before the cutoff. Load time and compression time are measured separately.
"""
import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone

from psycopg import sql

from db_config import get_connection

CAT = timezone(timedelta(hours=2), "CAT")
SOURCE = "energy_readings"                                   # cleaned daily table (the baseline)
TARGETS = ["energy_time_compressed", "energy_meter_compressed"]
EXPECTED_ROWS = 10_643_735                                   # cleaned row count from 2.3


def main():
    os.makedirs("results", exist_ok=True)

    # 4.1.4: ONE cutoff = experiment start minus 48 hours, used for BOTH tables.
    experiment_start = datetime.now(CAT)
    cutoff = experiment_start - timedelta(hours=48)
    print(f"Experiment start (CAT) : {experiment_start.isoformat(timespec='seconds')}")
    print(f"Cutoff (start - 48 h)  : {cutoff.isoformat(timespec='seconds')}")
    with open(os.path.join("results", "compression_experiment.json"), "w", encoding="utf-8") as f:
        json.dump({"experiment_start_cat": experiment_start.isoformat(timespec="seconds"),
                   "cutoff_cat": cutoff.isoformat(timespec="seconds")}, f, indent=2)

    conn = get_connection()
    conn.autocommit = True                      # every statement commits by itself
    cur = conn.cursor()

    # Both targets must be empty before loading.
    for target in TARGETS:
        n = cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(target))).fetchone()[0]
        if n != 0:
            raise SystemExit(f"STOP: {target} already holds {n} rows. It must be empty.")

    # The daily chunks of the source table. The targets use the same 1-day interval,
    # so each source chunk fills exactly one target chunk.
    chunks = cur.execute(
        "SELECT range_start, range_end FROM timescaledb_information.chunks "
        "WHERE hypertable_name = %s ORDER BY range_start", (SOURCE,)).fetchall()
    print(f"Source chunks          : {len(chunks)}")

    log = []                                    # one record per target and chunk
    for target in TARGETS:
        print(f"\n=== {target} ===")
        started = datetime.now(CAT)
        load_total = compress_total = 0.0
        rows_total = rows_compressed = chunks_compressed = 0

        for range_start, range_end in chunks:
            # ---- LOAD this chunk (timed) ----
            t0 = time.perf_counter()
            cur.execute(
                sql.SQL("INSERT INTO {} SELECT * FROM {} WHERE event_time >= %s AND event_time < %s")
                   .format(sql.Identifier(target), sql.Identifier(SOURCE)),
                (range_start, range_end))
            rows = cur.rowcount                 # original row count of this chunk
            load_s = time.perf_counter() - t0

            # ---- find the target chunk that was just filled ----
            found = cur.execute(
                "SELECT chunk_schema, chunk_name FROM timescaledb_information.chunks "
                "WHERE hypertable_name = %s AND range_start = %s", (target, range_start)).fetchone()

            # ---- COMPRESS it if its end precedes the cutoff (timed separately) ----
            compress_s, compressed = None, False
            if found and range_end < cutoff:
                full_name = f"{found[0]}.{found[1]}"
                t1 = time.perf_counter()
                cur.execute(sql.SQL("CALL convert_to_columnstore({})").format(sql.Literal(full_name)))
                compress_s = time.perf_counter() - t1
                compressed = True
                chunks_compressed += 1
                rows_compressed += rows
                compress_total += compress_s

            rows_total += rows
            load_total += load_s
            log.append({"table": target, "range_start": range_start.isoformat(timespec="minutes"),
                        "range_end": range_end.isoformat(timespec="minutes"), "rows": rows,
                        "load_seconds": round(load_s, 2), "compressed": compressed,
                        "compress_seconds": None if compress_s is None else round(compress_s, 2)})
            print(f"  {range_start:%Y-%m-%d %H:%M}  rows {rows:>8,}  load {load_s:6.1f} s  "
                  f"compress {'-' if compress_s is None else format(compress_s, '6.1f') + ' s'}")

        finished = datetime.now(CAT)
        stored = cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(target))).fetchone()[0]

        # Housekeeping so the planner has current statistics; reported separately, NOT part of the costs.
        t2 = time.perf_counter()
        cur.execute(sql.SQL("VACUUM (ANALYZE) {}").format(sql.Identifier(target)))
        housekeeping_s = time.perf_counter() - t2

        print(f"--- {target} SUMMARY ---")
        print(f"Started / finished (CAT)       : {started:%H:%M:%S} / {finished:%H:%M:%S}")
        print(f"Rows loaded / in table         : {rows_total:,} / {stored:,}   "
              f"({'MATCH' if stored == rows_total == EXPECTED_ROWS else 'MISMATCH'} with {EXPECTED_ROWS:,})")
        print(f"Load seconds (sum)             : {load_total:.1f}")
        print(f"Compression seconds (sum)      : {compress_total:.1f}   <- the compression cost for 4.2")
        print(f"Compressed chunks              : {chunks_compressed} of {len(chunks)}")
        print(f"Rows in compressed chunks      : {rows_compressed:,} = "
              f"{100 * rows_compressed / EXPECTED_ROWS:.2f}% of the cleaned rows")
        print(f"VACUUM ANALYZE (excluded)      : {housekeeping_s:.1f} s")

    with open(os.path.join("results", "compression_load_log.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(log[0].keys()))
        writer.writeheader()
        writer.writerows(log)
    print("\nSaved: results\\compression_load_log.csv and results\\compression_experiment.json")
    conn.close()


if __name__ == "__main__":
    main()