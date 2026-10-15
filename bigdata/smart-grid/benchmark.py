"""benchmark.py - Tasks 3.2 and 4.3: time the five workloads Q1-Q5 on one or more hypertables.

Usage (from the project folder):
    python benchmark.py --label chunks --tables energy_readings energy_readings_3h energy_readings_week

The FIRST table listed is the reference: every other table must return the same result
(numbers within 0.001). For every query and table: one warm-up run, then five measured runs.
The timer starts when the statement is submitted and stops when the last result row has been
received. PostgreSQL is never restarted and no cache is cleared, so these are WARM-CACHE results.
"""
import argparse
import csv
import os
import platform
import re
import socket
import statistics
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg

from db_config import get_connection

CAT = timezone(timedelta(hours=2), "CAT")     # every reported time is in CAT (+02:00)
MEASURED_RUNS = 5                             # measured runs after the single warm-up
TOLERANCE = 0.001                             # largest allowed numeric difference between tables

# The five workloads. {t} is replaced by the table name; nothing else changes between tables.
QUERIES = {
    # Q1: average power for each CAT hour on 21 September (all readings in that hour)
    "Q1": """
        SELECT date_trunc('hour', event_time) AS hour_cat, avg(power_kw) AS avg_power_kw
        FROM {t}
        WHERE event_time >= '2026-09-21 00:00:00+02' AND event_time < '2026-09-22 00:00:00+02'
        GROUP BY 1
        ORDER BY 1""",
    # Q2: the ten busiest 15-minute intervals from 22 to 28 September (network total power).
    #     Ties are broken by the earlier event_time, so exactly ten rows come back.
    "Q2": """
        SELECT event_time, sum(power_kw) AS total_power_kw
        FROM {t}
        WHERE event_time >= '2026-09-22 00:00:00+02' AND event_time < '2026-09-29 00:00:00+02'
        GROUP BY event_time
        ORDER BY total_power_kw DESC, event_time ASC
        LIMIT 10""",
    # Q3: total energy per meter over the whole period
    "Q3": """
        SELECT meter_id, sum(energy_kwh) AS total_energy_kwh
        FROM {t}
        GROUP BY meter_id
        ORDER BY meter_id""",
    # Q4: one meter, 22 to 28 September: total energy, average power, peak power
    "Q4": """
        SELECT sum(energy_kwh) AS total_energy_kwh, avg(power_kw) AS avg_power_kw,
               max(power_kw) AS peak_power_kw
        FROM {t}
        WHERE meter_id = 1000000000
          AND event_time >= '2026-09-22 00:00:00+02' AND event_time < '2026-09-29 00:00:00+02'""",
    # Q5: full scan: row count, total energy, average / minimum / maximum power
    "Q5": """
        SELECT count(*) AS n_rows, sum(energy_kwh) AS total_energy_kwh, avg(power_kw) AS avg_power_kw,
               min(power_kw) AS min_power_kw, max(power_kw) AS max_power_kw
        FROM {t}""",
}


def run_once(cur, sql):
    """Run one statement; return the rows, CAT start/end times and the timer readings."""
    start_cat = datetime.now(CAT)
    t_start = time.perf_counter()          # timer starts at statement submission
    cur.execute(sql)
    rows = cur.fetchall()                  # ...and stops once the last result row has arrived
    t_end = time.perf_counter()
    end_cat = datetime.now(CAT)
    return rows, start_cat, end_cat, t_start, t_end


def same_results(a, b):
    """True if two result sets match: identical keys, numbers within TOLERANCE."""
    if len(a) != len(b):
        return False
    for row_a, row_b in zip(a, b):
        for x, y in zip(row_a, row_b):
            if isinstance(x, (int, float, Decimal)) and isinstance(y, (int, float, Decimal)):
                if abs(float(x) - float(y)) > TOLERANCE:      # numeric: allow rounding noise
                    return False
            elif x != y:                                      # timestamps, ids: must be identical
                return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="name for the output files, e.g. chunks")
    parser.add_argument("--tables", nargs="+", required=True,
                        help="tables to time; the first one is the reference for correctness")
    args = parser.parse_args()
    for name in args.tables:               # table names are pasted into SQL, so check them first
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
            raise SystemExit(f"Unsafe table name: {name}")

    machine = socket.gethostname()                                    # machine identifier
    client = f"Python {platform.python_version()} + psycopg {psycopg.__version__}"
    timer = "time.perf_counter() around cursor.execute() + fetchall()"
    os.makedirs("results", exist_ok=True)

    conn = get_connection()
    conn.autocommit = True                 # no open transaction while timing; settings untouched
    cur = conn.cursor()
    server = cur.execute("SELECT version()").fetchone()[0]

    runs = []                              # one record per run, warm-up included
    summary = []                           # one record per (query, table)
    reference = {}                         # query -> rows returned by the first table
    first_start = None                     # timer reading at the first warm-up submission
    last_end = None                        # timer reading at the latest result
    session_start_cat = datetime.now(CAT)

    print(f"Benchmark '{args.label}' started {session_start_cat.isoformat(timespec='seconds')} on {machine}")
    for qname, template in QUERIES.items():
        for table in args.tables:
            sql = template.format(t=table)
            durations = []
            match = True
            for run_no in range(MEASURED_RUNS + 1):             # run 0 is the warm-up
                rows, s_cat, e_cat, t0, t1 = run_once(cur, sql)
                if first_start is None:
                    first_start = t0
                last_end = t1
                ms = (t1 - t0) * 1000
                if qname not in reference:
                    reference[qname] = rows                     # first table's first run = reference
                elif not same_results(reference[qname], rows):
                    match = False                               # any difference is reported
                kind = "warm-up" if run_no == 0 else "measured"
                if run_no > 0:
                    durations.append(ms)
                runs.append({"label": args.label, "query": qname, "table": table, "run_no": run_no,
                             "kind": kind, "start_cat": s_cat.isoformat(timespec="milliseconds"),
                             "end_cat": e_cat.isoformat(timespec="milliseconds"),
                             "duration_ms": round(ms, 2), "rows_returned": len(rows),
                             "machine": machine, "client": client})
            med = statistics.median(durations)
            summary.append({"query": qname, "table": table, "median_ms": round(med, 1),
                            "min_ms": round(min(durations), 1), "max_ms": round(max(durations), 1),
                            "rows": len(rows), "results_match_reference": match})
            print(f"  {qname} {table:<22} median {med:9.1f} ms   min {min(durations):9.1f}   "
                  f"max {max(durations):9.1f}   rows {len(rows):>5}   match {match}")

    session_seconds = last_end - first_start     # first warm-up submission -> last measured result
    session_end_cat = datetime.now(CAT)
    conn.close()

    # Save every individual run and the summary (these are the recorded benchmark timings).
    runs_path = os.path.join("results", f"benchmark_{args.label}_runs.csv")
    summary_path = os.path.join("results", f"benchmark_{args.label}_summary.csv")
    with open(runs_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        w.writeheader()
        w.writerows(runs)
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    # Comparison table: median milliseconds per query and table, fastest marked.
    print("\n=== COMPARISON: median ms of 5 measured warm-cache runs ===")
    print(f"{'Query':<6}" + "".join(f"{t:>24}" for t in args.tables) + f"{'fastest':>24}")
    for qname in QUERIES:
        meds = {r["table"]: r["median_ms"] for r in summary if r["query"] == qname}
        best = min(meds, key=meds.get)
        print(f"{qname:<6}" + "".join(f"{meds[t]:>24.1f}" for t in args.tables) + f"{best:>24}")

    print("\n=== SESSION RECORD ===")
    print(f"Measurements       : WARM-CACHE (1 warm-up + {MEASURED_RUNS} measured runs per query and table)")
    print(f"Client             : {client}")
    print(f"Timing tool        : {timer}")
    print(f"Machine            : {machine}")
    print(f"Server             : {server}")
    print(f"Session start/end  : {session_start_cat.isoformat(timespec='seconds')}  ->  "
          f"{session_end_cat.isoformat(timespec='seconds')}")
    print(f"Session seconds    : {session_seconds:.1f}  (first warm-up submission -> last measured result)")
    print(f"All results match  : {all(r['results_match_reference'] for r in summary)}")
    print(f"Saved              : {runs_path} and {summary_path}")


if __name__ == "__main__":
    main()