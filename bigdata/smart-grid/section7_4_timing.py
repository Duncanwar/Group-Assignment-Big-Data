"""
Assignment I, 7.4 - dashboard refresh timing, Raw vs Aggregate.

Tool: Playwright (Python) driving Google Chrome against Grafana 13.2.
Method per mode: open dashboard, 1 warm-up refresh, then N (default 10) measured refreshes.
  * per-panel query duration = browser request start -> last byte of that panel's /api/ds/query response
  * dashboard time = click on Refresh -> all five panel queries finished + two animation frames
    (render commit). This approximates "all five panels finished rendering".
Browser cache is disabled through Chrome DevTools. Grafana OSS has no query-result cache.

Before running: pause jobs (sql\\7_4_pause_jobs.sql), close other applications.
  $env:GRAFANA_USER = "admin"; $env:GRAFANA_PASSWORD = "<your grafana password>"
  python section7_4_timing.py            (add --headed to watch the browser)
"""
import argparse
import base64
import csv
import json
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

CAT = timezone(timedelta(hours=2))
PARAMS = ("orgId=1&from=2026-09-21T22:00:00.000Z&to=2026-09-28T22:00:00.000Z"
          "&timezone=Africa%2FKigali&var-start_date=2026-09-22"
          "&var-end_date=2026-09-29&var-meter_id=1000000000")
DASH = {"Raw": "raw-dash/raw", "Aggregate": "aggregate-dash/aggregate"}
NAMES = {1: "1 Hourly regional", 2: "2 Daily network", 3: "3 Seven-day period",
         4: "4 Selected meter", 5: "5 Completeness"}
RAF2 = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def classify(sql):
    """Map an interpolated panel query to panel number 1..5."""
    if "WITH reg AS" in sql:
        return 5
    if re.search(r"meter_id = (\d+|\$meter_id)", sql):
        return 4
    if "/ 7)" in sql:
        return 3
    if "AS metric" in sql:
        return 1
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grafana", default="http://localhost:3000")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()

    user = os.environ.get("GRAFANA_USER", "admin")
    pw = os.environ["GRAFANA_PASSWORD"]
    auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
    os.makedirs("results", exist_ok=True)

    print(f"7.4 timing started {now()} CAT")
    runs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not a.headed)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1500},
                                  extra_http_headers={"Authorization": f"Basic {auth}"})
        page = ctx.new_page()
        ctx.new_cdp_session(page).send("Network.setCacheDisabled", {"cacheDisabled": True})
        print(f"Browser: Chrome {browser.version}; viewport 1600x1500; cache disabled")

        rec, failed = {}, []

        def on_done(req):
            if "/api/ds/query" not in req.url:
                return
            try:
                sql = json.loads(req.post_data or "{}")["queries"][0].get("rawSql", "")
            except Exception:
                return
            resp = req.response()
            if resp is not None and resp.status >= 400:
                failed.append(f"HTTP {resp.status}")
            rec[classify(sql)] = req.timing["responseEnd"]

        def on_fail(req):
            if "/api/ds/query" in req.url:
                failed.append("request failed")

        page.on("requestfinished", on_done)
        page.on("requestfailed", on_fail)

        def wait_all(timeout=60):
            end = time.perf_counter() + timeout
            while len(rec) < 5 and time.perf_counter() < end:
                page.wait_for_timeout(5)
            if len(rec) < 5 or failed:
                raise RuntimeError(f"panels finished: {sorted(rec)}; errors: {failed}")
            page.evaluate(RAF2)

        def click_refresh():
            for loc in (page.locator('[data-testid="data-testid RefreshPicker run button"]'),
                        page.get_by_role("button", name="Refresh", exact=True)):
                if loc.count() > 0:
                    loc.first.click()
                    return
            raise RuntimeError("Refresh button not found")

        for mode, path in DASH.items():
            print(f"\n--- {mode}: load + 1 warm-up refresh + {a.runs} measured refreshes ---")
            rec.clear(); failed.clear()
            page.goto(f"{a.grafana}/d/{path}?{PARAMS}")
            wait_all()
            rec.clear(); click_refresh(); wait_all()          # warm-up refresh (not recorded)
            for i in range(1, a.runs + 1):
                page.wait_for_timeout(2000)                    # let the page settle between runs
                rec.clear()
                start = now(); t0 = time.perf_counter()
                click_refresh(); wait_all()
                total = (time.perf_counter() - t0) * 1000
                end = now()
                row = {"mode": mode, "run": i, "cat_start": start, "cat_end": end,
                       "dashboard_ms": round(total, 1)}
                for k in range(1, 6):
                    row[f"panel{k}_ms"] = round(rec[k], 1)
                runs.append(row)
                print(f"run {i:>2}: dashboard {total:8.1f} ms | " +
                      " ".join(f"p{k}={rec[k]:.0f}" for k in range(1, 6)))
        browser.close()

    cols = ["dashboard_ms"] + [f"panel{k}_ms" for k in range(1, 6)]
    with open("results/7_4_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["mode", "run", "cat_start", "cat_end"] + cols)
        w.writeheader(); w.writerows(runs)

    def stats(mode, col):
        v = [r[col] for r in runs if r["mode"] == mode]
        return statistics.median(v), min(v), max(v)

    print(f"\nSummary (ms; median / min / max of {a.runs} measured refreshes)")
    print(f"{'':<22}{'Raw median':>11}{'min':>9}{'max':>9}   {'Agg median':>11}{'min':>9}{'max':>9}   {'improvement':>11}")
    out = []
    for col, label in [(f"panel{k}_ms", NAMES[k]) for k in range(1, 6)] + [("dashboard_ms", "Whole dashboard")]:
        rm, rmin, rmax = stats("Raw", col)
        am, amin, amax = stats("Aggregate", col)
        imp = 100.0 * (rm - am) / rm
        print(f"{label:<22}{rm:>11.1f}{rmin:>9.1f}{rmax:>9.1f}   {am:>11.1f}{amin:>9.1f}{amax:>9.1f}   {imp:>10.1f}%")
        out.append([label, rm, rmin, rmax, am, amin, amax, imp])
    with open("results/7_4_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "raw_median", "raw_min", "raw_max", "agg_median", "agg_min", "agg_max",
                    "improvement_pct"])
        w.writerows(out)
    print("\nPositive improvement = Aggregate faster than Raw.")
    print("Aggregate cost from 6.1: 107.8 s total initial refresh; 18,866,176 bytes (~18.0 MB) stored.")
    print(f"Done {now()} CAT. Runs saved in results\\7_4_runs.csv, summary in results\\7_4_summary.csv")


if __name__ == "__main__":
    main()
