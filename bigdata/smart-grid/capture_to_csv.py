"""capture_to_csv.py - Task 2.1: capture the full generator stream into a CSV file for bulk loading."""
import csv
import json
import os
import time
from datetime import datetime

import smart_meter_simulator as sim          # the unchanged generator

OUT_DIR = "data"                              # stays local; never committed to GitHub
CSV_PATH = os.path.join(OUT_DIR, "readings.csv")
STATS_PATH = os.path.join(OUT_DIR, "capture_stats.json")
PROGRESS_EVERY = 500_000                      # print a progress line every this many rows


def now_cat():
    # Local time with its offset (+02:00 = CAT), recorded for the report.
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. Record the data contract and expected counts (task 2.1.1).
    info = sim.dataset_info()
    fields = info["reading_fields"]                       # the eight column names, in order
    expected = info["expected_counts"]["emitted_readings"]
    print("Generator version     :", info["generator_version"])
    print("Planned readings      :", info["planned_readings"])
    print("Expected counts       :", info["expected_counts"])

    started_cat = now_cat()
    t0 = time.perf_counter()                              # high-resolution timer for elapsed seconds
    print(f"Capture started (CAT) : {started_cat}")

    # 2. Start a FRESH iterator and write every dictionary as one CSV row, progressively.
    #    Nothing is collected in a list, so memory use stays small.
    consumed = 0
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")       # "\n" keeps COPY loading simple
        writer.writerow(fields)                           # header row
        for record in sim.iter_readings():
            writer.writerow([record[name] for name in fields])
            consumed += 1
            if consumed % PROGRESS_EVERY == 0:
                elapsed = time.perf_counter() - t0
                pct = 100 * consumed / expected
                print(f"  {consumed:>10,} rows  {pct:5.1f}%  {elapsed:7.1f} s")

    generation_seconds = time.perf_counter() - t0
    finished_cat = now_cat()

    # 3. Compare with the expected emitted count (task 2.1.3).
    status = "MATCH" if consumed == expected else "MISMATCH"
    size_gb = os.path.getsize(CSV_PATH) / 1024**3
    print("---------------- CAPTURE SUMMARY ----------------")
    print(f"Dictionaries consumed      : {consumed:,}")
    print(f"Expected emitted_readings  : {expected:,}   -> {status}")
    print(f"CSV data rows written      : {consumed:,}  (plus 1 header row)")
    print(f"File                       : {CSV_PATH}  ({size_gb:.2f} GB)")
    print(f"Finished (CAT)             : {finished_cat}")
    print(f"Generation + file seconds  : {generation_seconds:.1f}")

    # 4. Save the numbers for the report and for the loader to reuse.
    with open(STATS_PATH, "w", encoding="utf-8") as g:
        json.dump({"route": "CSV + COPY", "started_cat": started_cat, "finished_cat": finished_cat,
                   "consumed": consumed, "expected_emitted": expected,
                   "generation_seconds": round(generation_seconds, 1)}, g, indent=2)


if __name__ == "__main__":
    main()