"""Generate exploratory joint scenarios from the repository's available data.

No PV forecast-error or local-plant data are available.  This module creates
an explicitly synthetic proxy and is not suitable for commercial validation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DA_FILE = ROOT / "data" / "raw" / "day_ahead_prices.csv"
PV_FILE = ROOT / "data" / "pv_profile_10mw_2026-08-06_15min.csv"


def load_da_prices(path: Path = DA_FILE) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    price_col = [c for c in df.columns if c.startswith("Germany/Luxembourg")][0]
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df["Start date"], format="%b %d, %Y %I:%M %p"),
            "da_price_eur_mwh": pd.to_numeric(df[price_col], errors="coerce"),
        }
    ).dropna()


def load_pv_proxy(path: Path = PV_FILE) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df.rename(
        columns={
            "timestamp": "source_timestamp_utc",
            "p_pv_mw": "p_pv_forecast_mw",
        }
    )[["source_timestamp_utc", "pv_national_mw", "p_pv_forecast_mw"]]


def generate_scenarios(
    n_scenarios: int = 100,
    horizon_steps: int = 672,
    block_length: int = 288,
    seed: int = 42,
) -> pd.DataFrame:
    if n_scenarios <= 0:
        raise ValueError("n_scenarios must be positive")
    if horizon_steps <= 0:
        raise ValueError("horizon_steps must be positive")
    if block_length <= 0:
        raise ValueError("block_length must be positive")

    da = load_da_prices()
    pv = load_pv_proxy()
    rng = np.random.default_rng(seed)

    da_starts = np.arange(0, len(da) - block_length + 1)
    pv_values = pv["p_pv_forecast_mw"].to_numpy()
    pv_national = pv["pv_national_mw"].to_numpy()

    rows = []
    for scenario_id in range(n_scenarios):
        da_indices = []
        pv_indices = []
        while len(da_indices) < horizon_steps:
            start = int(rng.choice(da_starts))
            take = min(block_length, horizon_steps - len(da_indices))
            da_indices.extend(range(start, start + take))
            pv_indices.extend(
                (np.arange(len(pv_indices), len(pv_indices) + take) % len(pv_values)).tolist()
            )

        for step, (da_idx, pv_idx) in enumerate(zip(da_indices, pv_indices)):
            forecast = float(pv_values[pv_idx])
            forecast_national = float(pv_national[pv_idx])
            error_mw = float(
                rng.normal(loc=0.0, scale=max(0.05 * forecast, 0.05))
            )
            actual = float(np.clip(forecast + error_mw, 0.0, 10.0))
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "step": step,
                    "block_id": step // block_length,
                    "source_timestamp_utc": da.iloc[da_idx]["timestamp"].isoformat(),
                    "da_price_eur_mwh": float(
                        da.iloc[da_idx]["da_price_eur_mwh"]
                    ),
                    "pv_forecast_mwh_15min": forecast * 0.25,
                    "pv_actual_mwh_15min": actual * 0.25,
                    "pv_error_mwh_15min": (actual - forecast) * 0.25,
                    "scenario_weight": 1.0 / n_scenarios,
                    "pv_actual_national_mw": (
                        actual * (forecast_national / forecast)
                        if forecast > 0
                        else 0.0
                    ),
                    "pv_forecast_national_mw": forecast_national,
                    "p_pv_mw": actual,
                    "p_pv_forecast_mw": forecast,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-scenarios", type=int, default=100)
    parser.add_argument("--horizon-steps", type=int, default=672)
    parser.add_argument("--block-length", type=int, default=288)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "data"
        / "processed"
        / "hybrid_scenarios_10mw_v1.csv",
    )
    args = parser.parse_args()
    scenarios = generate_scenarios(
        args.n_scenarios,
        args.horizon_steps,
        args.block_length,
        args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scenarios.to_csv(args.output, index=False)
    print(f"Wrote {len(scenarios)} rows to {args.output}")


if __name__ == "__main__":
    main()
