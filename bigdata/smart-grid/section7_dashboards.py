"""
Assignment I, Section 7 helper.

  python section7_dashboards.py build    -> dashboards/Raw.json, dashboards/Aggregate.json (Grafana import)
  python section7_dashboards.py verify   -> 7.3 numerical comparison of every panel, Raw vs Aggregate

Both modes use the SAME panel SQL below, so dashboards and checks cannot drift apart.
Run from the smart-grid folder with DB_PASSWORD set (verify needs the database).
"""
import argparse
import csv
import json
import os
from datetime import datetime, timedelta, timezone

CAT = timezone(timedelta(hours=2))
TZ = "Africa/Kigali"


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def rng(col):
    return (f"{col} >= '$start_date'::date::timestamp AT TIME ZONE '{TZ}'\n"
            f"  AND {col} < '$end_date'::date::timestamp AT TIME ZONE '{TZ}'")


RAW_EXTRA = ",\n       count(*) AS readings"
AGG_EXTRA = ",\n       sum(c.reading_count) AS readings"

PANELS = [
    dict(
        id=1, title="Hourly regional energy (kWh)", type="timeseries", fmt="time_series",
        unit="kwatth", keys=["time", "metric"], val="Energy (kWh)", tol=0.001,
        extra_raw=RAW_EXTRA, extra_agg=AGG_EXTRA,
        raw="""SELECT time_bucket(INTERVAL '1 hour', r.event_time, 'Africa/Kigali') AS "time",
       m.region AS metric,
       sum(r.energy_kwh) AS "Energy (kWh)"{extra}
FROM energy_readings r
JOIN meters m ON m.meter_id = r.meter_id
WHERE {range}
GROUP BY 1, 2
ORDER BY 1, 2""",
        agg="""SELECT c.bucket AS "time",
       c.region AS metric,
       sum(c.sum_energy_kwh) AS "Energy (kWh)"{extra}
FROM cagg_hourly_region c
WHERE {range}
GROUP BY 1, 2
ORDER BY 1, 2""",
    ),
    dict(
        id=2, title="Daily network energy (kWh)", type="barchart", fmt="table",
        unit="kwatth", keys=["day"], val="Energy (kWh)", tol=0.001,
        extra_raw=RAW_EXTRA, extra_agg=AGG_EXTRA,
        raw="""SELECT (r.event_time AT TIME ZONE 'Africa/Kigali')::date::text AS day,
       sum(r.energy_kwh) AS "Energy (kWh)"{extra}
FROM energy_readings r
WHERE {range}
GROUP BY 1
ORDER BY 1""",
        agg="""SELECT (c.bucket AT TIME ZONE 'Africa/Kigali')::date::text AS day,
       sum(c.sum_energy_kwh) AS "Energy (kWh)"{extra}
FROM cagg_15min_region c
WHERE {range}
GROUP BY 1
ORDER BY 1""",
    ),
    dict(
        id=3, title="Network energy per seven-day period (kWh)", type="barchart", fmt="table",
        unit="kwatth", keys=["period_start"], val="Energy (kWh)", tol=0.001,
        extra_raw=RAW_EXTRA, extra_agg=AGG_EXTRA,
        raw="""SELECT to_char(DATE '2026-09-01' + 7 * (((r.event_time AT TIME ZONE 'Africa/Kigali')::date - DATE '2026-09-01') / 7), 'YYYY-MM-DD') AS period_start,
       sum(r.energy_kwh) AS "Energy (kWh)"{extra}
FROM energy_readings r
WHERE {range}
GROUP BY 1
ORDER BY 1""",
        agg="""SELECT to_char(DATE '2026-09-01' + 7 * (((c.bucket AT TIME ZONE 'Africa/Kigali')::date - DATE '2026-09-01') / 7), 'YYYY-MM-DD') AS period_start,
       sum(c.sum_energy_kwh) AS "Energy (kWh)"{extra}
FROM cagg_15min_region c
WHERE {range}
GROUP BY 1
ORDER BY 1""",
    ),
    dict(
        id=4, title="Daily energy for selected meter (kWh)", type="barchart", fmt="table",
        unit="kwatth", keys=["day"], val="Energy (kWh)", tol=0.001,
        extra_raw=RAW_EXTRA, extra_agg=AGG_EXTRA,
        raw="""SELECT (r.event_time AT TIME ZONE 'Africa/Kigali')::date::text AS day,
       sum(r.energy_kwh) AS "Energy (kWh)"{extra}
FROM energy_readings r
WHERE r.meter_id = $meter_id
  AND {range}
GROUP BY 1
ORDER BY 1""",
        agg="""SELECT (c.bucket AT TIME ZONE 'Africa/Kigali')::date::text AS day,
       sum(c.sum_energy_kwh) AS "Energy (kWh)"{extra}
FROM cagg_daily_meter c
WHERE c.meter_id = $meter_id
  AND {range}
GROUP BY 1
ORDER BY 1""",
    ),
    dict(
        id=5, title="Completeness by region (%)", type="barchart", fmt="table",
        unit="percent", keys=["region"], val="Completeness (%)", tol=0.000001,
        extra_raw=", obs.observed AS readings", extra_agg=", obs.observed AS readings",
        raw="""WITH reg AS (SELECT region, count(*) AS meters FROM meters GROUP BY region),
obs AS (
  SELECT m.region, count(*) AS observed
  FROM energy_readings r
  JOIN meters m ON m.meter_id = r.meter_id
  WHERE {range}
  GROUP BY m.region)
SELECT reg.region,
       100.0 * obs.observed / (reg.meters * (('$end_date'::date - '$start_date'::date) * 96)) AS "Completeness (%)"{extra}
FROM reg
JOIN obs ON obs.region = reg.region
ORDER BY reg.region""",
        agg="""WITH reg AS (SELECT region, count(*) AS meters FROM meters GROUP BY region),
obs AS (
  SELECT c.region, sum(c.reading_count) AS observed
  FROM cagg_15min_region c
  WHERE {range}
  GROUP BY c.region)
SELECT reg.region,
       100.0 * obs.observed / (reg.meters * (('$end_date'::date - '$start_date'::date) * 96)) AS "Completeness (%)"{extra}
FROM reg
JOIN obs ON obs.region = reg.region
ORDER BY reg.region""",
    ),
]

LAYOUT = {1: (0, 0, 24, 9), 2: (0, 9, 12, 8), 3: (12, 9, 12, 8),
          4: (0, 17, 12, 8), 5: (12, 17, 12, 8)}


def render(p, mode, with_readings):
    """mode: 'raw' or 'agg'. with_readings adds the reading-count column used by verify."""
    col = "r.event_time" if mode == "raw" else "c.bucket"
    extra = p["extra_" + mode] if with_readings else ""
    return p[mode].format(extra=extra, range=rng(col))


def textbox(name, label, value):
    return {"name": name, "label": label, "type": "textbox", "query": value,
            "current": {"text": value, "value": value},
            "options": [{"selected": True, "text": value, "value": value}]}


def dashboard_json(title, uid, mode):
    panels = []
    for p in PANELS:
        x, y, w, h = LAYOUT[p["id"]]
        panel = {
            "id": p["id"], "title": p["title"], "type": p["type"],
            "description": f"{title} mode: " + ("reads energy_readings directly"
                                               if mode == "raw" else "reads continuous aggregate views"),
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"refId": "A", "format": p["fmt"], "rawQuery": True,
                         "editorMode": "code", "rawSql": render(p, mode, False)}],
            "fieldConfig": {"defaults": {"unit": p["unit"]}, "overrides": []},
            "options": {},
        }
        if p["type"] == "barchart":
            panel["options"] = {"legend": {"showLegend": False}, "showValue": "auto"}
        panels.append(panel)
    return {
        "uid": uid, "title": title, "tags": ["assignment-i", mode],
        "schemaVersion": 39, "version": 1, "editable": True,
        "timezone": TZ, "refresh": "",
        # 22 Sep 00:00 CAT to 29 Sep 00:00 CAT, written in UTC
        "time": {"from": "2026-09-21T22:00:00.000Z", "to": "2026-09-28T22:00:00.000Z"},
        "templating": {"list": [
            textbox("start_date", "Start day (CAT, inclusive)", "2026-09-22"),
            textbox("end_date", "End day (CAT, exclusive)", "2026-09-29"),
            textbox("meter_id", "Meter", "1000000000"),
        ]},
        "panels": panels,
    }


def build():
    os.makedirs("dashboards", exist_ok=True)
    for title, uid, mode in (("Raw", "raw-dash", "raw"), ("Aggregate", "aggregate-dash", "agg")):
        path = f"dashboards/{title}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dashboard_json(title, uid, mode), f, indent=2)
        print("wrote", path)
    print("Import both in Grafana (Dashboards > New > Import). Set the smart_meters "
          "PostgreSQL data source as default first. Time picker: 22 Sep 00:00 - 29 Sep 00:00 CAT.")


def verify(start, end, meter):
    from db_config import get_connection
    os.makedirs("results", exist_ok=True)

    def sub(sql):
        return (sql.replace("$start_date", start).replace("$end_date", end)
                .replace("$meter_id", str(meter)))

    def run(cur, sql):
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        return cols, cur.fetchall()

    def save(path, cols, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)

    print(f"7.3 verification started {now()}")
    print(f"Range: {start} 00:00 CAT to {end} 00:00 CAT (exclusive); meter {meter}")
    summary = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET timezone = 'Africa/Kigali'")
            for p in PANELS:
                res = {}
                for mode in ("raw", "agg"):
                    cols, rows = run(cur, sub(render(p, mode, True)))
                    res[mode] = (cols, rows)
                    save(f"results/7_3_panel{p['id']}_{mode}.csv", cols, rows)

                def index(cols, rows):
                    ki = [cols.index(k) for k in p["keys"]]
                    vi, ri = cols.index(p["val"]), cols.index("readings")
                    return {tuple(r[i] for i in ki): (float(r[vi]), int(r[ri])) for r in rows}

                a, b = index(*res["raw"]), index(*res["agg"])
                same_keys = set(a) == set(b)
                common = set(a) & set(b)
                maxdiff = max((abs(a[k][0] - b[k][0]) for k in common), default=float("nan"))
                same_counts = all(a[k][1] == b[k][1] for k in common)
                ok = same_keys and same_counts and maxdiff <= p["tol"]
                summary.append((p["id"], p["title"], len(common), same_keys, same_counts,
                                maxdiff, p["tol"], ok))

    print(f"\n{'Panel':<45}{'rows':>6}{'keys=':>7}{'counts=':>9}{'max |diff|':>14}{'tol':>10}  result")
    for pid, title, n, sk, sc, md, tol, ok in summary:
        print(f"{pid}. {title:<42}{n:>6}{str(sk):>7}{str(sc):>9}{md:>14.9f}{tol:>10}  "
              f"{'PASS' if ok else 'FAIL'}")
    print(f"\nPer-panel CSVs saved in results\\ (7_3_panel<N>_raw.csv / _agg.csv). Done {now()}")
    if not all(s[-1] for s in summary):
        print("At least one panel FAILED: investigate before any timing.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "verify"])
    ap.add_argument("--start", default="2026-09-22")
    ap.add_argument("--end", default="2026-09-29")
    ap.add_argument("--meter", type=int, default=1000000000)
    a = ap.parse_args()
    build() if a.mode == "build" else verify(a.start, a.end, a.meter)
