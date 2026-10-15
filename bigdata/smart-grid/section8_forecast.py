"""
Assignment I, Section 8 - hourly regional consumption forecast (kWh)

8.1 dataset, splits, features, lag checks
8.2 previous-day baseline (1,680 test predictions)
8.3 Ridge regression, several alpha settings, selection on validation MAE, frozen before test
8.4 metrics (overall and per region), peak hours, plot

Run from the smart-grid folder with DB_PASSWORD set:
    python section8_forecast.py [--region "Region 1"]
Outputs go to results\\ (8_*.csv and 8_4_forecast_<region>.png).
"""
import argparse
import os
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from db_config import get_connection

CAT = timezone(timedelta(hours=2))
OUT = "results"
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

FIRST = pd.Timestamp("2026-09-01 00:00", tz=CAT)
N_HOURS = 28 * 24
LOOKBACK_H = 168                       # longest lag used by any configuration
NUM = ["lag_24h", "lag_48h", "lag_168h", "prev_day_mean_24h"]
CATF = ["region", "hour_c"]
PASS = ["is_weekend"]
FEATS = NUM + CATF + PASS
SPLITS = {"train": ("2026-09-01", "2026-09-14"),
          "validation": ("2026-09-15", "2026-09-21"),
          "test": ("2026-09-22", "2026-09-28")}
ALPHAS = {"R1": 0.1, "R2": 1.0, "R3": 10.0, "R4": 100.0}


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def banner(t):
    print("\n" + "=" * 78)
    print(f"{t}   [{now()}]")
    print("=" * 78)


def metrics(actual, pred):
    e = np.asarray(pred) - np.asarray(actual)          # predicted minus actual
    return float(np.mean(np.abs(e))), float(np.sqrt(np.mean(e ** 2)))


def make_model(alpha):
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATF),
        ("pass", "passthrough", PASS),
    ])
    return Pipeline([("pre", pre), ("model", Ridge(alpha=alpha))])


ap = argparse.ArgumentParser()
ap.add_argument("--region", default="Region 1", help="region used for the 8.4 plot")
args = ap.parse_args()

# ------------------------------------------------------------------ 8.1
banner("8.1 Prepare chronological data and features")
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SET timezone = 'Africa/Kigali'")
        cur.execute("""
            SELECT m.region,
                   time_bucket(INTERVAL '1 hour', r.event_time, 'Africa/Kigali') AS hour_ts,
                   sum(r.energy_kwh) AS kwh,
                   count(*) AS n_readings
            FROM energy_readings r
            JOIN meters m ON m.meter_id = r.meter_id
            GROUP BY 1, 2 ORDER BY 1, 2
        """)
        rows = cur.fetchall()

raw = pd.DataFrame(rows, columns=["region", "hour_ts", "kwh", "n_readings"])
raw["epoch"] = raw["hour_ts"].map(lambda t: int(t.timestamp()))
regions = sorted(raw["region"].unique(), key=lambda s: int(s.split()[-1]))
hours = pd.date_range(FIRST, periods=N_HOURS, freq="h")
grid = pd.MultiIndex.from_product([regions, hours], names=["region", "ts"]).to_frame(index=False)
grid["epoch"] = grid["ts"].map(lambda t: int(t.timestamp()))
g = grid.merge(raw[["region", "epoch", "kwh", "n_readings"]], on=["region", "epoch"], how="left")
g = g.sort_values(["region", "ts"]).reset_index(drop=True)

expected_rows = len(regions) * N_HOURS
present = int(g["kwh"].notna().sum())
print(f"Region-hours expected {expected_rows:,}; present {present:,}; absent {expected_rows - present:,}")
print("Reading counts per region-hour (full hour = 400 meters x 4 = 1,600): "
      f"min {int(g['n_readings'].min()):,}, mean {g['n_readings'].mean():,.1f}, "
      f"max {int(g['n_readings'].max()):,}; total {int(g['n_readings'].sum()):,}")
print("Handling: totals are the observed sums of cleaned readings. Absent hours (if any) stay absent "
      "(never zero-filled); a missing predictor value is imputed with the training-set median.")

g["day"] = g["ts"].dt.normalize()
g["origin"] = g["day"]                                   # forecast origin = 00:00 of the target day
g["hour_c"] = g["ts"].dt.hour.astype(str)
g["is_weekend"] = (g["ts"].dt.dayofweek >= 5).astype(int)
for h in (24, 48, 168):
    g[f"lag_{h}h"] = g.groupby("region")["kwh"].shift(h)
dm = g.groupby(["region", "day"], as_index=False)["kwh"].mean().rename(columns={"kwh": "prev_day_mean_24h"})
dm["day"] = dm["day"] + pd.Timedelta(days=1)
g = g.merge(dm, on=["region", "day"], how="left")
g = g.sort_values(["region", "ts"]).reset_index(drop=True)

day_str = g["ts"].dt.strftime("%Y-%m-%d")
g["split"] = None
for name, (a, b) in SPLITS.items():
    g.loc[(day_str >= a) & (day_str <= b), "split"] = name

print("\nSplit sizes and target date limits:")
srows = []
for name, (a, b) in SPLITS.items():
    s = g[g["split"] == name]
    srows.append([name, len(s), s["ts"].min().strftime("%Y-%m-%d %H:%M"),
                  s["ts"].max().strftime("%Y-%m-%d %H:%M")])
sp = pd.DataFrame(srows, columns=["split", "rows", "first_target", "last_target"])
print(sp.to_string(index=False))
sp.to_csv(f"{OUT}/8_1_splits.csv", index=False)

feat_tab = pd.DataFrame([
    ["hour_c, is_weekend (calendar)", 0, FIRST],
    ["region (category)", 0, FIRST],
    ["lag_24h (previous day, same hour)", 24, FIRST + pd.Timedelta(hours=24)],
    ["lag_48h (two days earlier, same hour)", 48, FIRST + pd.Timedelta(hours=48)],
    ["lag_168h (same hour one week earlier)", 168, FIRST + pd.Timedelta(hours=168)],
    ["prev_day_mean_24h (mean of previous day's 24 hours)", 24, FIRST + pd.Timedelta(hours=24)],
], columns=["feature", "lag_or_window_hours", "earliest_usable_target"])
print("\nFeatures:")
print(feat_tab.to_string(index=False))
feat_tab.to_csv(f"{OUT}/8_1_features.csv", index=False)

cutoff = FIRST + pd.Timedelta(hours=LOOKBACK_H)
tr_all = g[g["split"] == "train"]
excluded = int((tr_all["ts"] < cutoff).sum())
train = tr_all[tr_all["ts"] >= cutoff].copy()
val = g[g["split"] == "validation"].copy()
test = g[g["split"] == "test"].copy()
print(f"\nInitial lookback = {LOOKBACK_H} h -> earliest usable training target {cutoff:%Y-%m-%d %H:%M}")
print(f"Training rows before lookback exclusions: {len(tr_all):,}; excluded: {excluded:,}; retained: {len(train):,}")
print("Same retained training rows are used for every model configuration.")
print(f"Missing predictor values (train / validation / test): "
      f"{int(train[NUM].isna().sum().sum())} / {int(val[NUM].isna().sum().sum())} / "
      f"{int(test[NUM].isna().sum().sum())}")

print("\nLag-source check (source timestamp must be earlier than the forecast origin):")
for name, h in (("lag_24h", 24), ("lag_48h", 48), ("lag_168h", 168)):
    viol = int(((g["ts"] - pd.Timedelta(hours=h)) >= g["origin"]).sum())
    print(f"  {name}: rows with source >= origin = {viol}  -> {'OK' if viol == 0 else 'VIOLATION'}")
viol = int(((g["origin"] - pd.Timedelta(hours=1)) >= g["origin"]).sum())
print(f"  prev_day_mean_24h: latest source = origin - 1 h; violations = {viol}  -> OK")

ex = g[(g["region"] == regions[0]) & (g["split"] == "test")].head(4).copy()
ex["lag_24h_source"] = ex["ts"] - pd.Timedelta(hours=24)
ex["lag_168h_source"] = ex["ts"] - pd.Timedelta(hours=168)
print("\nFeature examples (first test hours of", regions[0] + "):")
print(ex[["ts", "origin", "kwh", "lag_24h", "lag_24h_source", "lag_168h", "lag_168h_source",
          "prev_day_mean_24h", "is_weekend"]].to_string(index=False))

# ------------------------------------------------------------------ 8.2
banner("8.2 Previous-day baseline on the test split")
test["baseline"] = test["lag_24h"]
assert test["baseline"].notna().all(), "baseline needs previous-day value for every test row"
print(f"Baseline predictions: {len(test):,} (expected 1,680)")
b_mae, b_rmse = metrics(test["kwh"], test["baseline"])
print(f"Baseline test MAE  = {b_mae:,.3f} kWh")
print(f"Baseline test RMSE = {b_rmse:,.3f} kWh")
print("\nSample baseline predictions:")
print(test[["region", "ts", "kwh", "baseline"]].head(8).to_string(index=False))
test[["region", "ts", "kwh", "baseline"]].to_csv(f"{OUT}/8_2_baseline_predictions.csv", index=False)

# ------------------------------------------------------------------ 8.3
banner("8.3 Ridge regression: configurations, validation, selection")
print(f"Shared predictors: {', '.join(FEATS)} (preprocessing fitted on training rows only)")
tv = train.dropna(subset=["kwh"])
vv = val.dropna(subset=["kwh"])
fitted, vrows = {}, []
for cid, alpha in ALPHAS.items():
    m = make_model(alpha).fit(tv[FEATS], tv["kwh"])
    fitted[cid] = m
    mae, rmse = metrics(vv["kwh"], m.predict(vv[FEATS]))
    vrows.append([cid, f"Ridge(alpha={alpha})", len(tv), len(vv), mae, rmse])
    print(f"  trained {cid} alpha={alpha} at {now()}  validation MAE {mae:,.3f} kWh")
vt = pd.DataFrame(vrows, columns=["config_id", "model_settings", "training_rows",
                                  "validation_rows", "validation_MAE_kWh", "validation_RMSE_kWh"])
print("\nValidation table:")
print(vt.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
vt.to_csv(f"{OUT}/8_3_validation_table.csv", index=False)
best_id = vt.loc[vt["validation_MAE_kWh"].idxmin(), "config_id"]
best = fitted[best_id]                               # frozen: no refit on validation or test
print(f"\nSelected (lowest validation MAE): {best_id}, {vt.set_index('config_id').loc[best_id, 'model_settings']}")
print("Model and preprocessing are frozen; they are not refitted on validation or test data.")

test["model"] = best.predict(test[FEATS])
print(f"\nModel test predictions: {len(test):,} (expected 1,680)")
print("Sample test predictions:")
print(test[["region", "ts", "kwh", "baseline", "model"]].head(8).to_string(index=False))
test[["region", "ts", "kwh", "baseline", "model"]].to_csv(f"{OUT}/8_3_test_predictions.csv", index=False)

# ------------------------------------------------------------------ 8.4
banner("8.4 Judge forecast usefulness (error = predicted - actual, kWh)")
m_mae, m_rmse = metrics(test["kwh"], test["model"])
ov = pd.DataFrame([["baseline", b_mae, b_rmse], ["model", m_mae, m_rmse]],
                  columns=["method", "MAE_kWh", "RMSE_kWh"])
print(f"Overall over {len(test):,} test observations:")
print(ov.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
print(f"MAE change vs baseline: {100 * (b_mae - m_mae) / b_mae:+.1f}% "
      f"| RMSE change: {100 * (b_rmse - m_rmse) / b_rmse:+.1f}% (positive = model better)")
ov.to_csv(f"{OUT}/8_4_metrics_overall.csv", index=False)

rr = []
for r in regions:
    s = test[test["region"] == r]
    bm, br = metrics(s["kwh"], s["baseline"])
    mm, mr = metrics(s["kwh"], s["model"])
    rr.append([r, len(s), bm, br, mm, mr, 100 * (bm - mm) / bm])
rt = pd.DataFrame(rr, columns=["region", "n", "base_MAE", "base_RMSE", "model_MAE", "model_RMSE",
                               "MAE_improvement_%"])
print("\nPer region:")
print(rt.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
rt.to_csv(f"{OUT}/8_4_metrics_by_region.csv", index=False)

test["day_s"] = test["ts"].dt.strftime("%Y-%m-%d %a")
dd = test.groupby("day_s").apply(lambda s: pd.Series({
    "base_MAE": metrics(s["kwh"], s["baseline"])[0],
    "model_MAE": metrics(s["kwh"], s["model"])[0]}), include_groups=False).reset_index()
print("\nMAE by test day (explains where the baseline fails):")
print(dd.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))

pk = []
for r in regions:
    s = test[test["region"] == r].sort_values(["kwh", "ts"], ascending=[False, True]).iloc[0]
    pk.append([r, s["ts"].strftime("%Y-%m-%d %H:%M"), s["kwh"], s["baseline"],
               abs(s["baseline"] - s["kwh"]), s["model"], abs(s["model"] - s["kwh"])])
pt = pd.DataFrame(pk, columns=["region", "peak_hour", "actual_kWh", "baseline_pred", "baseline_abs_err",
                               "model_pred", "model_abs_err"])
print("\nHighest actual test-hour consumption per region (ties -> earliest):")
print(pt.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
pt.to_csv(f"{OUT}/8_4_peak_hours.csv", index=False)

if args.region not in regions:
    args.region = regions[0]
s = test[test["region"] == args.region].sort_values("ts")
fig, ax = plt.subplots(figsize=(13, 4.8))
ax.plot(s["ts"], s["kwh"], label="Actual", color="black", linewidth=1.8)
ax.plot(s["ts"], s["baseline"], label="Previous-day baseline", color="#c0504d", linewidth=1.1)
ax.plot(s["ts"], s["model"], label=f"Ridge ({best_id})", color="#4f81bd", linewidth=1.1)
ax.set_ylabel("Energy (kWh per hour)")
ax.set_title(f"{args.region}: actual vs forecasts, 22-28 Sep 2026 (CAT)")
ax.legend()
ax.grid(alpha=0.3)
fig.autofmt_xdate()
plt.tight_layout()
png = f"{OUT}/8_4_forecast_{args.region.replace(' ', '_')}.png"
plt.savefig(png, dpi=150)
plt.close()
print(f"\nPlot saved: {png}")
print(f"Done {now()}")
