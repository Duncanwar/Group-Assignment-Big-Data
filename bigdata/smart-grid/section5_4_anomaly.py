"""
Assignment I, Section 5.4 - abnormal consumption detection

RULE (fixed BEFORE labels are loaded):
  1. reference(customer_type, event_time) = mean power_kw of all meters of that
     customer type at that event_time. This removes the shared daily pattern,
     weekday/weekend effect and network growth trend.
  2. ratio = meter power_kw / reference.
  3. For each meter: median ratio and MAD (scaled by 1.4826) of its own ratios.
  4. deviation = |ratio - median| / MAD. Flag the reading if deviation > K_MAIN.
  K_MAIN = 6 is a conservative a-priori cut-off (not tuned on labels).
  Both spikes and drops/outages are flagged (two-sided).

Labels (anomaly_events) are imported and used only in the evaluation step.
Run from the smart-grid folder with DB_PASSWORD set.
"""
import io
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from db_config import get_connection

CAT = timezone(timedelta(hours=2))
OUT = "results"
os.makedirs(OUT, exist_ok=True)

K_MAIN = 6.0
K_SENS = [4.0, 5.0, 6.0, 8.0, 10.0]   # sensitivity, for discussion only
MAD_FLOOR = 1e-4
N_METERS = 4000


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def banner(t):
    print("\n" + "=" * 78)
    print(f"{t}   [{now()}]")
    print("=" * 78)


# ---------------------------------------------------------------- load data
print(f"5.4 started {now()}")
with get_connection() as conn:
    sql = ("COPY (SELECT meter_id, extract(epoch FROM event_time)::bigint AS t, "
           "power_kw FROM energy_readings) TO STDOUT WITH (FORMAT CSV)")
    buf = io.BytesIO()
    with conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for chunk in copy:
                buf.write(chunk)
        buf.seek(0)
        df = pd.read_csv(buf, names=["meter_id", "t", "power_kw"],
                         dtype={"meter_id": "int64", "t": "int64", "power_kw": "float64"})
        cur.execute("SELECT meter_id, customer_type FROM meters")
        meters = pd.DataFrame(cur.fetchall(), columns=["meter_id", "customer_type"])

df = df.merge(meters, on="meter_id", how="left")
assert df["customer_type"].notna().all(), "readings without metadata"
df["customer_type"] = df["customer_type"].astype("category")
print(f"Loaded {len(df):,} cleaned readings for {df['meter_id'].nunique():,} meters at {now()}")

# ---------------------------------------------------------------- detection
banner("Detection (rule applied to cleaned readings, labels not yet loaded)")
df["ref"] = df.groupby(["customer_type", "t"], observed=True)["power_kw"].transform("mean")
df["ratio"] = df["power_kw"] / df["ref"]
med = df.groupby("meter_id")["ratio"].transform("median")
absdev = (df["ratio"] - med).abs()
mad = absdev.groupby(df["meter_id"]).transform("median") * 1.4826
mad = np.maximum(mad, MAD_FLOOR)
df["dev"] = absdev / mad
dev = df["dev"].to_numpy()
mid = df["meter_id"].to_numpy()
t = df["t"].to_numpy()

flag_main = dev > K_MAIN
print(f"Threshold K = {K_MAIN}; flagged readings: {int(flag_main.sum()):,} "
      f"({100 * flag_main.mean():.4f}% of readings); "
      f"meters with >=1 flag: {len(np.unique(mid[flag_main])):,}")

# ---------------------------------------------------------------- evaluation
banner("Evaluation against anomaly_events() (labels used only here)")
from smart_meter_simulator import anomaly_events  # noqa: E402


def to_epoch(x):
    if isinstance(x, str):
        x = datetime.fromisoformat(x)
    return int(x.timestamp())


events = anomaly_events()
ev = pd.DataFrame([{
    "meter_id": int(e["meter_id"]), "event_type": e["event_type"],
    "start": to_epoch(e["start_time"]), "end": to_epoch(e["end_time"]),
    "start_time": str(e["start_time"]), "end_time": str(e["end_time"]),
} for e in events])
print(f"Events supplied: {len(ev)}")

inside = np.zeros(len(df), dtype=bool)
ev_idx = []
for e in ev.itertuples():
    idx = np.flatnonzero((mid == e.meter_id) & (t >= e.start) & (t < e.end))
    ev_idx.append(idx)
    inside[idx] = True
outside_n = int((~inside).sum())
print(f"Observed readings inside injected intervals: {int(inside.sum()):,}; "
      f"outside: {outside_n:,}")


def evaluate(k):
    flag = dev > k
    detected = [bool(flag[idx].any()) for idx in ev_idx]
    false_mask = flag & ~inside
    fn = int(false_mask.sum())
    aff = len(np.unique(mid[false_mask]))
    return {
        "K": k, "detected": sum(detected), "missed": len(ev) - sum(detected),
        "false_flags": fn, "false_pct_of_outside": 100.0 * fn / outside_n,
        "meters_with_false_flag": aff,
        "pct_meters_affected_by_false_flags": 100.0 * aff / N_METERS,
    }, detected, false_mask


main, detected, false_mask = evaluate(K_MAIN)

ev["detected"] = detected
ev["n_readings_in_interval"] = [len(i) for i in ev_idx]
ev["n_flags_inside"] = [int(flag_main[i].sum()) for i in ev_idx]
ev["max_dev_inside"] = [float(dev[i].max()) if len(i) else np.nan for i in ev_idx]
ev.to_csv(f"{OUT}/5_4_event_comparison.csv", index=False)
print("\nPer-event comparison (K = %.1f):" % K_MAIN)
print(ev[["meter_id", "event_type", "start_time", "end_time", "n_readings_in_interval",
          "n_flags_inside", "max_dev_inside", "detected"]].to_string(
    index=False, float_format=lambda x: f"{x:,.1f}"))

print(f"\nDetected events : {main['detected']} of {len(ev)}")
print(f"Missed events   : {main['missed']} of {len(ev)}")
print(f"False flags     : {main['false_flags']:,} "
      f"= {main['false_pct_of_outside']:.5f}% of {outside_n:,} observed readings outside injected intervals")
print(f"Meters with >=1 false flag: {main['meters_with_false_flag']:,} "
      f"= {main['pct_meters_affected_by_false_flags']:.3f}% of {N_METERS:,} "
      f"(percentage of meters affected by false flags)")

if main["missed"]:
    print("\nMissed events (for the explanation):")
    print(ev.loc[~ev["detected"], ["meter_id", "event_type", "start_time", "end_time",
                                   "n_readings_in_interval", "max_dev_inside"]].to_string(index=False))

if main["false_flags"]:
    fdf = df.loc[false_mask, ["customer_type", "meter_id", "t"]].copy()
    print("\nFalse flags by customer type:")
    print(fdf["customer_type"].value_counts().to_string())
    hours = pd.to_datetime(fdf["t"], unit="s", utc=True).dt.tz_convert(CAT).dt.hour
    print("\nFalse flags by CAT hour:")
    print(hours.value_counts().sort_index().to_string())
    print("\nFalse flags per meter (top 10):")
    print(fdf["meter_id"].value_counts().head(10).to_string())

# ---------------------------------------------------------------- save flags
fl = df.loc[flag_main, ["meter_id", "t", "power_kw", "ref", "ratio", "dev"]].copy()
fl["event_time"] = pd.to_datetime(fl["t"], unit="s", utc=True).dt.tz_convert(CAT)
fl["inside_injected_interval"] = inside[flag_main]
fl = fl.drop(columns="t").sort_values("dev", ascending=False)
fl.to_csv(f"{OUT}/5_4_flags.csv", index=False)
print(f"\nSaved {len(fl):,} flagged readings to {OUT}\\5_4_flags.csv")
print("Top 10 flagged readings by deviation:")
print(fl.head(10)[["meter_id", "event_time", "power_kw", "ratio", "dev",
                   "inside_injected_interval"]].to_string(index=False, float_format=lambda x: f"{x:,.3f}"))

# ---------------------------------------------------------------- sensitivity
banner("Sensitivity (discussion only; primary threshold was fixed in advance)")
sens = pd.DataFrame([evaluate(k)[0] for k in K_SENS])
sens.to_csv(f"{OUT}/5_4_sensitivity.csv", index=False)
print(sens.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
print(f"\nDone {now()}")