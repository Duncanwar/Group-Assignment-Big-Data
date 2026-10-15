"""section4_facts.py - Tasks 4.2, 4.3 and 4.4: gathers every measured number in one place
and drafts the 4.4 text from them.

Needs (produced by the earlier steps):
  results/compression_load_log.csv     (compress_load.py)
  results/benchmark_all_summary.csv    (benchmark.py --label all ...)
Sizes and the policy status are read straight from the database.
"""
import csv
import os

from db_config import get_connection

BASE, TIME_T, METER_T = "energy_readings", "energy_time_compressed", "energy_meter_compressed"
LOG = os.path.join("results", "compression_load_log.csv")
BENCH = os.path.join("results", "benchmark_all_summary.csv")
MB = 1024 * 1024


def need(path, hint):
    # Stop with a clear message if an earlier step has not been run yet.
    if not os.path.exists(path):
        raise SystemExit(f"Missing {path}. {hint}")


def describe(new_ms, old_ms):
    """'12.3% faster' or '12.3% slower': `new_ms` compared with `old_ms`."""
    change = 100 * (old_ms - new_ms) / old_ms
    return f"{abs(change):.1f}% {'faster' if change > 0 else 'slower'}"


def main():
    need(LOG, "Run compress_load.py first.")
    need(BENCH, "Run: python benchmark.py --label all --tables energy_readings energy_readings_3h "
                "energy_readings_week energy_time_compressed energy_meter_compressed")

    # ---- compression log: load/compression seconds, chunk and row counts per table ----
    stats = {t: {"load_s": 0.0, "comp_s": 0.0, "chunks": 0, "comp_chunks": 0, "rows": 0, "rows_comp": 0}
             for t in (TIME_T, METER_T)}
    with open(LOG, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = stats[r["table"]]
            s["chunks"] += 1
            s["rows"] += int(r["rows"])
            s["load_s"] += float(r["load_seconds"])
            if r["compressed"] == "True":            # only compressed chunks have a compression time
                s["comp_chunks"] += 1
                s["rows_comp"] += int(r["rows"])
                s["comp_s"] += float(r["compress_seconds"])

    # ---- sizes (all chunks and indexes) and policy status, from the database ----
    conn = get_connection()
    cur = conn.cursor()
    size = {}
    for t in (BASE, TIME_T, METER_T):
        tb, ib, tob, tot = cur.execute(
            "SELECT table_bytes, index_bytes, toast_bytes, total_bytes "
            "FROM hypertable_detailed_size(%s::regclass)", (t,)).fetchone()
        size[t] = {"data": ((tb or 0) + (tob or 0)) / MB, "index": (ib or 0) / MB, "total": (tot or 0) / MB}
    jobs = cur.execute(
        "SELECT hypertable_name, scheduled FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_compression' AND hypertable_name IN (%s, %s)", (TIME_T, METER_T)).fetchall()
    conn.close()

    # ---- benchmark medians ----
    med = {}
    with open(BENCH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            med[(r["query"], r["table"])] = float(r["median_ms"])
    queries = sorted({q for q, _ in med})
    for q in queries:
        for t in (BASE, TIME_T, METER_T):
            if (q, t) not in med:
                raise SystemExit(f"{BENCH} has no result for {q} on {t}. Re-run the 'all' benchmark.")

    # ---- 4.2: storage and compression cost ----
    b = size[BASE]["total"]
    print("=== 4.2 STORAGE AND COMPRESSION COST (baseline = uncompressed daily table) ===")
    print(f"{'table':<26}{'data MB':>10}{'index MB':>10}{'total MB':>10}{'ratio':>8}{'saved %':>9}"
          f"{'compress s':>12}{'compr. chunks':>15}{'rows in compr. %':>18}")
    print(f"{BASE:<26}{size[BASE]['data']:>10.1f}{size[BASE]['index']:>10.1f}{b:>10.1f}")
    for t in (TIME_T, METER_T):
        s, z = stats[t], size[t]
        print(f"{t:<26}{z['data']:>10.1f}{z['index']:>10.1f}{z['total']:>10.1f}"
              f"{b / z['total']:>8.2f}{100 * (b - z['total']) / b:>9.1f}{s['comp_s']:>12.1f}"
              f"{str(s['comp_chunks']) + ' of ' + str(s['chunks']):>15}"
              f"{100 * s['rows_comp'] / s['rows']:>18.2f}")
    print(f"Load seconds (not part of the compression cost): "
          f"{TIME_T} {stats[TIME_T]['load_s']:.1f} s, {METER_T} {stats[METER_T]['load_s']:.1f} s")

    # ---- 4.3: medians and percentage improvement versus the daily baseline ----
    print("\n=== 4.3 MEDIAN ms AND IMPROVEMENT vs DAILY BASELINE (positive % = faster) ===")
    print(f"{'Query':<7}{'baseline':>10}{'time-ordered':>15}{'improv %':>10}{'meter-segmented':>18}{'improv %':>10}")
    for q in queries:
        base, mt, mm = med[(q, BASE)], med[(q, TIME_T)], med[(q, METER_T)]
        print(f"{q:<7}{base:>10.1f}{mt:>15.1f}{100 * (base - mt) / base:>+10.1f}"
              f"{mm:>18.1f}{100 * (base - mm) / base:>+10.1f}")

    # ---- 4.4: draft text built from the numbers above ----
    single = "Q4"                                          # the only single-meter workload
    multi = [q for q in queries if q != single]            # Q1, Q2, Q3, Q5 touch all meters
    wins_meter = sum(med[(q, METER_T)] < med[(q, TIME_T)] for q in queries)
    print("\n=== DRAFT 4.4 (check every claim against the tables above, then edit) ===")
    print("4.4.1 Effect of meter segmentation (meter-segmented table versus time-ordered table)")
    print(f"  Single-meter workload {single}: {med[(single, METER_T)]:.1f} ms versus "
          f"{med[(single, TIME_T)]:.1f} ms, so {describe(med[(single, METER_T)], med[(single, TIME_T)])} "
          f"with meter segmentation.")
    for q in multi:
        print(f"  All-meter workload {q}: {med[(q, METER_T)]:.1f} ms versus {med[(q, TIME_T)]:.1f} ms "
              f"({describe(med[(q, METER_T)], med[(q, TIME_T)])} with meter segmentation).")

    # Rule used for the draft recommendation: the strategy that is faster on more of the five
    # queries wins; if they tie, the smaller total size wins. Change it if you judge differently.
    if wins_meter * 2 > len(queries):
        pick = METER_T
    elif wins_meter * 2 < len(queries):
        pick = TIME_T
    else:
        pick = min((TIME_T, METER_T), key=lambda t: size[t]["total"])
    other = METER_T if pick == TIME_T else TIME_T
    name = {TIME_T: "time-ordered columnstore compression with no segmentation",
            METER_T: "columnstore compression segmented by meter_id (ordered by event_time DESC)"}
    wins = wins_meter if pick == METER_T else len(queries) - wins_meter
    z, s, so = size[pick], stats[pick], stats[other]
    print("\n4.4.2 Recommendation")
    print(f"  Choose 1-day chunks with {name[pick]}.")
    print(f"  Evidence: total size {z['total']:.1f} MB against {b:.1f} MB uncompressed "
          f"(ratio {b / z['total']:.2f}, {100 * (b - z['total']) / b:.1f}% saved); it was faster than the other "
          f"strategy on {wins} of {len(queries)} queries (Q4 {med[(single, pick)]:.1f} ms against "
          f"{med[(single, BASE)]:.1f} ms uncompressed; Q3 {med[('Q3', pick)]:.1f} ms against "
          f"{med[('Q3', BASE)]:.1f} ms).")
    lost = [q for q in queries if med[(q, pick)] > med[(q, other)]]
    slower_than_base = [q for q in queries if med[(q, pick)] > med[(q, BASE)]]
    print(f"  Tradeoff (compression time): compressing the {s['comp_chunks']} chunks took {s['comp_s']:.1f} s, "
          f"{s['comp_s'] / so['comp_s']:.2f} times the {so['comp_s']:.1f} s of the alternative; "
          f"this is a one-off cost paid before the storage saving appears.")
    print(f"  Tradeoff (workload): it is slower than the alternative on {lost if lost else 'no query'} "
          f"and slower than the uncompressed table on {slower_than_base if slower_than_base else 'no query'}.")

    # ---- reminder about the paused policies ----
    print("\n=== POLICY STATUS ===")
    for name_, scheduled in jobs:
        print(f"  {name_}: {'enabled' if scheduled else 'PAUSED (resume it after the 4.3 measurements)'}")


if __name__ == "__main__":
    main()