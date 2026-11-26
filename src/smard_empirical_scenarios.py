"""Joint empirical DA-price and PV scenarios from SMARD data.

The national PV series is peak-normalized to a hypothetical plant capacity.
This is a research proxy, not a local plant forecast.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = (
    ROOT / "data" / "processed" / "smard_joint_clean_15min_v2.csv"
)
DEFAULT_OUTPUT = (
    ROOT / "data" / "processed" / "smard_empirical_scenarios_10mw_v1.csv"
)
DEFAULT_METADATA = (
    ROOT / "data" / "processed"
    / "smard_empirical_scenarios_10mw_v1_metadata.json"
)

REQUIRED_COLUMNS = [
    "timestamp_utc",
    "da_price_eur_mwh",
    "pv_actual_mw",
    "pv_forecast_mw",
]


def _contiguous_segments(
    frame: pd.DataFrame,
    interval_minutes: int = 15,
) -> list[pd.DataFrame]:
    """Split observations at missing timestamps."""
    timestamps = frame["timestamp_utc"]
    expected = pd.Timedelta(minutes=interval_minutes)

    segment_id = timestamps.diff().ne(expected).cumsum()

    return [
        group.reset_index(drop=True)
        for _, group in frame.groupby(segment_id, sort=False)
    ]


def generate_empirical_scenarios(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    metadata_path: Path = DEFAULT_METADATA,
    n_scenarios: int = 100,
    horizon_steps: int = 96,
    block_length: int = 96,
    seed: int = 42,
    capacity_mw: float = 10.0,
    train_cutoff_local: str = "2026-08-01T00:00:00+02:00",
) -> pd.DataFrame:

    if min(n_scenarios, horizon_steps, block_length) <= 0:
        raise ValueError("Scenario count, horizon and block length must be positive")

    if capacity_mw <= 0:
        raise ValueError("capacity_mw must be positive")

    frame = pd.read_csv(input_path)

    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    frame["timestamp_utc"] = pd.to_datetime(
        frame["timestamp_utc"], utc=True, errors="raise"
    )

    for col in ["da_price_eur_mwh", "pv_actual_mw", "pv_forecast_mw"]:
        frame[col] = pd.to_numeric(frame[col], errors="raise")

    frame = frame.sort_values("timestamp_utc").reset_index(drop=True)

    if frame["timestamp_utc"].duplicated().any():
        raise ValueError("Duplicate UTC timestamps found")

    if frame[REQUIRED_COLUMNS[1:]].isna().any().any():
        raise ValueError("Missing values found in required numeric columns")

    cutoff_utc = pd.Timestamp(train_cutoff_local).tz_convert("UTC")

    train = frame.loc[
        frame["timestamp_utc"] < cutoff_utc
    ].copy().reset_index(drop=True)

    if train.empty:
        raise ValueError("No training observations before cutoff")

    if (train["pv_actual_mw"] < 0).any():
        raise ValueError("Negative PV actual values found")

    if (train["pv_forecast_mw"] < 0).any():
        raise ValueError("Negative PV forecast values found")

    # One common scale for both actual and forecast PV.
    # This creates a normalized national proxy, not a local plant model.
    national_peak = float(
        max(
            train["pv_actual_mw"].max(),
            train["pv_forecast_mw"].max(),
        )
    )

    if not np.isfinite(national_peak) or national_peak <= 0:
        raise ValueError("Invalid national PV peak in training data")

    pv_scale = capacity_mw / national_peak

    segments = _contiguous_segments(train)

    # Candidate blocks are drawn only from uninterrupted 15-minute periods.
    candidates = [
        (segment, start)
        for segment in segments
        if len(segment) >= block_length
        for start in range(len(segment) - block_length + 1)
    ]

    if not candidates:
        raise ValueError(
            f"No uninterrupted training segment can provide "
            f"a block of {block_length} steps"
        )

    rng = np.random.default_rng(seed)
    records = []

    for scenario_id in range(n_scenarios):
        pieces = []
        remaining = horizon_steps

        while remaining > 0:
            segment, start = candidates[
                int(rng.integers(0, len(candidates)))
            ]

            take = min(block_length, remaining)
            pieces.append(segment.iloc[start:start + take].copy())
            remaining -= take

        path = pd.concat(pieces, ignore_index=True)

        actual = path["pv_actual_mw"].to_numpy(dtype=float) * pv_scale
        forecast = path["pv_forecast_mw"].to_numpy(dtype=float) * pv_scale

        for step in range(horizon_steps):
            records.append({
                "scenario_id": scenario_id,
                "step": step,
                "source_timestamp_utc": (
                    path.loc[step, "timestamp_utc"].isoformat()
                ),
                "da_price_eur_mwh": float(
                    path.loc[step, "da_price_eur_mwh"]
                ),
                "pv_forecast_national_mw": float(
                    path.loc[step, "pv_forecast_mw"]
                ),
                "pv_actual_national_mw": float(
                    path.loc[step, "pv_actual_mw"]
                ),
                "pv_forecast_error_national_mw": float(
                    path.loc[step, "pv_actual_mw"]
                    - path.loc[step, "pv_forecast_mw"]
                ),
                "p_pv_forecast_mw": float(forecast[step]),
                "p_pv_mw": float(actual[step]),
                "pv_error_mw": float(actual[step] - forecast[step]),
                "scenario_weight": 1.0 / n_scenarios,
            })

    scenarios = pd.DataFrame(records)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    scenarios.to_csv(output_path, index=False)

    metadata = {
        "source": "Bundesnetzagentur / SMARD",
        "input_file": str(input_path.relative_to(ROOT)),
        "output_file": str(output_path.relative_to(ROOT)),
        "method": "Joint moving-block bootstrap",
        "training_cutoff_local": train_cutoff_local,
        "training_cutoff_utc": cutoff_utc.isoformat(),
        "training_rows": int(len(train)),
        "n_scenarios": n_scenarios,
        "horizon_steps": horizon_steps,
        "block_length": block_length,
        "interval_minutes": 15,
        "seed": seed,
        "scenario_weight": 1.0 / n_scenarios,
        "pv_proxy_capacity_mw": capacity_mw,
        "national_pv_peak_training_mw": national_peak,
        "pv_normalization_factor": pv_scale,
        "pv_actual_definition": "SMARD national actual PV scaled by common factor",
        "pv_forecast_definition": "SMARD national day-ahead PV forecast scaled by common factor",
        "pv_error_definition": "actual minus forecast",
        "sampling": (
            "Price, PV actual and PV forecast are sampled jointly "
            "from the same historical timestamps. Blocks do not cross "
            "missing timestamp gaps."
        ),
        "limitations": [
            "National PV forecast errors are not local plant forecast errors.",
            "The 10 MW series is a peak-normalized national proxy.",
            "The model's imbalance price assumption remains a separate limitation.",
            "The scenario model does not by itself establish out-of-sample performance.",
        ],
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return scenarios


if __name__ == "__main__":
    result = generate_empirical_scenarios()

    print("Generated empirical joint scenarios")
    print("Rows:", len(result))
    print("Scenarios:", result["scenario_id"].nunique())
    print("Steps per scenario:", result.groupby("scenario_id").size().unique())
    print("PV actual range:", result["p_pv_mw"].min(), result["p_pv_mw"].max())
    print("PV forecast range:", result["p_pv_forecast_mw"].min(), result["p_pv_forecast_mw"].max())
    print("Price range:", result["da_price_eur_mwh"].min(), result["da_price_eur_mwh"].max())
    print("Output:", DEFAULT_OUTPUT)
    print("Metadata:", DEFAULT_METADATA)
