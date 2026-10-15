"""
Assignment I, Sections 5.1 - 5.3
Run from C:\\Users\\ebyiringiro\\smart-grid\\ with DB_PASSWORD set.
Writes charts and CSVs to results\\ and prints everything you need to screenshot.
"""
import os
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from db_config import get_connection

CAT = timezone(timedelta(hours=2))
OUT = "results"
os.makedirs(OUT, exist_ok=True)

START = "2026-09-01 00:00:00+02"
END = "2026-09-29 00:00:00+02"      # exclusive
METERS = 4000
DAYS = 28
PER_DAY = 96


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def q(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def banner(t):
    print("\n" + "=" * 78)
    print(f"{t}   [{now()}]")
    print("=" * 78)


with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SET timezone = 'Africa/Kigali'")

    print(f"Section 5 analysis started {now()}")

    # ------------------------------------------------------------------ 5.1
    banner("5.1 Network totals per 15-minute interval (one scan)")
    net = q(conn, """
        SELECT event_time, sum(power_kw) AS kw, sum(energy_kwh) AS kwh,
               count(*) AS n_readings
        FROM energy_readings
        WHERE event_time >= %s AND event_time < %s
        GROUP BY event_time ORDER BY event_time
    """, (START, END))
    net["event_time"] = pd.to_datetime(net["event_time"], utc=True).dt.tz_convert(CAT)
    net["day"] = net["event_time"].dt.tz_localize(None).dt.normalize()
    net["hour"] = net["event_time"].dt.hour
    net["weekend"] = net["event_time"].dt.dayofweek >= 5
    print(f"Intervals returned: {len(net)} (planned {DAYS * PER_DAY})")

    daily = net.groupby("day", as_index=False)["kwh"].sum()
    daily["weekday"] = daily["day"].dt.day_name()
    daily.to_csv(f"{OUT}/5_1_daily_energy.csv", index=False)
    print("\nDaily network energy (kWh):")
    print(daily.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    daily["week_no"] = (daily["day"] - pd.Timestamp("2026-09-01")).dt.days // 7
    weekly = daily.groupby("week_no")["kwh"].sum().reset_index()
    weekly["period_start"] = [
        (pd.Timestamp("2026-09-01") + pd.Timedelta(days=7 * i)).strftime("%d %b")
        for i in weekly["week_no"]
    ]
    weekly["period_end"] = [
        (pd.Timestamp("2026-09-07") + pd.Timedelta(days=7 * i)).strftime("%d %b")
        for i in weekly["week_no"]
    ]
    weekly.to_csv(f"{OUT}/5_1_weekly_energy.csv", index=False)
    print("\nSeven-day period totals (kWh):")
    print(weekly[["period_start", "period_end", "kwh"]].to_string(
        index=False, float_format=lambda x: f"{x:,.2f}"))

    top3 = net.sort_values(["kw", "event_time"], ascending=[False, True]).head(3)
    top3[["event_time", "kw", "n_readings"]].to_csv(f"{OUT}/5_1_top3_peaks.csv", index=False)
    print("\nThree highest 15-minute network demand intervals (kW):")
    print(top3[["event_time", "kw", "n_readings"]].to_string(
        index=False, float_format=lambda x: f"{x:,.2f}"))
    print("(n_readings < 4000 means missing readings lowered that interval's sum)")

    prof = net.groupby(["weekend", "hour"])["kw"].mean().unstack(0)
    prof.columns = ["weekday_avg_kw", "weekend_avg_kw"]
    prof.to_csv(f"{OUT}/5_1_hourly_profile.csv")
    print("\nAverage network kW by CAT hour (weekday vs weekend):")
    print(prof.to_string(float_format=lambda x: f"{x:,.1f}"))

    # charts
    fig, ax = plt.subplots(figsize=(11, 4.5))
    colors = ["#c0504d" if d >= 5 else "#4f81bd" for d in daily["day"].dt.dayofweek]
    ax.bar(daily["day"].dt.strftime("%d %b"), daily["kwh"], color=colors)
    ax.set_ylabel("Energy (kWh)")
    ax.set_title("Total network energy per CAT day (red = weekend)")
    plt.xticks(rotation=60)
    plt.tight_layout()
    plt.savefig(f"{OUT}/5_1_daily_energy.png", dpi=150)
    plt.close()

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(weekly["period_start"] + " - " + weekly["period_end"], weekly["kwh"], color="#4f81bd")
    ax.set_ylabel("Energy (kWh)")
    ax.set_title("Network energy per seven-day period")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(f"{OUT}/5_1_weekly_energy.png", dpi=150)
    plt.close()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(prof.index, prof["weekday_avg_kw"], marker="o", label="Weekday")
    ax.plot(prof.index, prof["weekend_avg_kw"], marker="s", label="Weekend")
    ax.set_xlabel("Hour of day (CAT)")
    ax.set_ylabel("Mean network demand (kW)")
    ax.set_title("Average daily demand profile")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{OUT}/5_1_hourly_profile.png", dpi=150)
    plt.close()
    print(f"\nCharts saved in {OUT}\\ at {now()}")

    # ------------------------------------------------------------------ 5.2
    banner("5.2 Regions and customer types (normalised by registered meters)")
    for col, label in (("region", "Region"), ("customer_type", "Customer type")):
        df = q(conn, f"""
            SELECT m.{col} AS grp,
                   mc.meters AS registered_meters,
                   sum(r.energy_kwh) AS total_kwh
            FROM energy_readings r
            JOIN meters m USING (meter_id)
            JOIN (SELECT {col} AS g, count(*) AS meters FROM meters GROUP BY {col}) mc
              ON mc.g = m.{col}
            WHERE r.event_time >= %s AND r.event_time < %s
            GROUP BY m.{col}, mc.meters
            ORDER BY m.{col}
        """, (START, END))
        df["kwh_per_meter"] = df["total_kwh"] / df["registered_meters"]
        df.to_csv(f"{OUT}/5_2_by_{col}.csv", index=False)
        print(f"\n{label}: totals, meter counts, energy per meter (28 days)")
        print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
        print(f"Check: registered meters sum = {df['registered_meters'].sum()}")

    cross = q(conn, """
        SELECT m.region, m.customer_type, count(DISTINCT m.meter_id) AS meters,
               sum(r.energy_kwh) / count(DISTINCT m.meter_id) AS kwh_per_meter
        FROM energy_readings r JOIN meters m USING (meter_id)
        WHERE r.event_time >= %s AND r.event_time < %s
        GROUP BY m.region, m.customer_type ORDER BY 1, 2
    """, (START, END))
    cross.to_csv(f"{OUT}/5_2_region_x_customer.csv", index=False)
    print("\nExtra: region x customer type (helps explain regional differences):")
    print(cross.pivot(index="region", columns="customer_type",
                      values="kwh_per_meter").to_string(float_format=lambda x: f"{x:,.1f}"))
    print(cross.pivot(index="region", columns="customer_type",
                      values="meters").to_string())

    # ------------------------------------------------------------------ 5.3
    banner("5.3 Reporting quality")
    dup = q(conn, """
        SELECT count(*) AS duplicate_pairs FROM (
          SELECT meter_id, event_time FROM energy_readings
          GROUP BY 1, 2 HAVING count(*) > 1) d
    """)
    print(f"Duplicate pairs in cleaned table (must be 0): {int(dup.iloc[0, 0])}")

    comp = q(conn, """
        SELECT m.region, mc.meters AS registered_meters, count(*) AS observed_unique
        FROM energy_readings r
        JOIN meters m USING (meter_id)
        JOIN (SELECT region AS g, count(*) AS meters FROM meters GROUP BY region) mc
          ON mc.g = m.region
        WHERE r.event_time >= %s AND r.event_time < %s
        GROUP BY m.region, mc.meters ORDER BY m.region
    """, (START, END))
    comp["planned"] = comp["registered_meters"] * DAYS * PER_DAY
    comp["completeness_pct"] = 100.0 * comp["observed_unique"] / comp["planned"]
    tot_obs = int(comp["observed_unique"].sum())
    tot_plan = METERS * DAYS * PER_DAY
    comp.loc[len(comp)] = ["NETWORK", METERS, tot_obs, tot_plan, 100.0 * tot_obs / tot_plan]
    comp.to_csv(f"{OUT}/5_3_completeness.csv", index=False)
    print("\nCompleteness (observed unique / planned), 28 days:")
    print(comp.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    print(f"Network planned = {METERS} x {DAYS} x {PER_DAY} = {tot_plan:,} "
          f"(expected 10,752,000); observed = {tot_obs:,} (expected 10,643,735)")

    cutoff = "2026-09-22 00:00:00+02"
    d21 = q(conn, """
        SELECT
          sum(energy_kwh) FILTER (WHERE received_time <= %s) AS cutoff_total,
          sum(energy_kwh)                                    AS final_total,
          count(*) FILTER (WHERE received_time <= %s)        AS cutoff_rows,
          count(*)                                           AS final_rows
        FROM energy_readings
        WHERE event_time >= %s AND event_time < %s
    """, (cutoff, cutoff, "2026-09-21 00:00:00+02", cutoff))
    r = d21.iloc[0]
    diff = r["final_total"] - r["cutoff_total"]
    pct = 100.0 * diff / r["final_total"]
    print("\n21 September daily total (event_time on 21 Sep):")
    print(f"  Received by 00:00 on 22 Sep : {r['cutoff_total']:,.3f} kWh  ({int(r['cutoff_rows']):,} rows)")
    print(f"  All arrivals                : {r['final_total']:,.3f} kWh  ({int(r['final_rows']):,} rows)")
    print(f"  Difference                  : {diff:,.3f} kWh  = {pct:.4f}% of final total")
    pd.DataFrame([{
        "cutoff_total_kwh": r["cutoff_total"], "final_total_kwh": r["final_total"],
        "difference_kwh": diff, "difference_pct_of_final": pct,
        "cutoff_rows": int(r["cutoff_rows"]), "final_rows": int(r["final_rows"]),
    }]).to_csv(f"{OUT}/5_3_day21_cutoff.csv", index=False)

    print(f"\nDone {now()}. Screenshot each section's output with the taskbar and clock visible.")