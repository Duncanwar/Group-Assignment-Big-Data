"""improvement.py - Task 4.3.2: percentage improvement of each compressed table over the daily baseline."""
import csv

BASELINE = "energy_readings"                                          # uncompressed, same 1-day interval
COMPRESSED = ["energy_time_compressed", "energy_meter_compressed"]

rows = list(csv.DictReader(open("results/benchmark_all_summary.csv", encoding="utf-8")))
median = {(r["query"], r["table"]): float(r["median_ms"]) for r in rows}

print("improvement % = 100 x (baseline median - compressed median) / baseline median   (positive = faster)")
print(f"{'Query':<6}{'baseline ms':>13}" + "".join(f"{t:>34}" for t in COMPRESSED))
for q in sorted({r["query"] for r in rows}):
    base = median[(q, BASELINE)]
    cells = ""
    for t in COMPRESSED:
        m = median[(q, t)]
        pct = 100 * (base - m) / base
        cells += f"{m:>14.1f} ms  ({pct:>+8.1f}%)  "
    print(f"{q:<6}{base:>13.1f}{cells}")