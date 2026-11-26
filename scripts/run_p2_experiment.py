"""Run a diagnostic BESS experiment using empirical or supplied scenarios.

The default input is the empirical SMARD joint-scenario dataset.
Imbalance prices equal DA prices only as a diagnostic assumption.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hybrid_bess_optimization import ScenarioDependentBESSModel


DEFAULT_CSV = (
    ROOT / "data" / "processed"
    / "smard_empirical_scenarios_10mw_v1.csv"
)


def run_experiment(
    csv_path: Path,
    n_scenarios: int,
    horizon: int,
    curtail_cost: float,
    max_imbalance: float = 10.0,
):
    if n_scenarios <= 0 or horizon <= 0:
        raise ValueError("n_scenarios and horizon must be positive")

    df = pd.read_csv(csv_path)

    required = {
        "scenario_id",
        "step",
        "p_pv_mw",
        "da_price_eur_mwh",
        "scenario_weight",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    ids = sorted(df["scenario_id"].unique())
    if len(ids) < n_scenarios:
        raise ValueError(
            f"Requested {n_scenarios} scenarios, but only {len(ids)} exist"
        )

    ids = ids[:n_scenarios]
    df = df[df["scenario_id"].isin(ids)].copy()

    p_pv = []
    lambda_da = []
    raw_weights = []

    for scenario_id in ids:
        frame = (
            df[df["scenario_id"] == scenario_id]
            .sort_values("step")
            .reset_index(drop=True)
        )

        if len(frame) < horizon:
            raise ValueError(
                f"Scenario {scenario_id} has {len(frame)} rows; "
                f"{horizon} required"
            )

        frame = frame.iloc[:horizon]

        if frame["step"].tolist() != list(range(horizon)):
            raise ValueError(
                f"Scenario {scenario_id} has missing or unordered steps"
            )

        if frame[["p_pv_mw", "da_price_eur_mwh", "scenario_weight"]].isna().any().any():
            raise ValueError(f"Scenario {scenario_id} contains missing values")

        weights = frame["scenario_weight"].astype(float).unique()
        if len(weights) != 1 or weights[0] <= 0:
            raise ValueError(
                f"Scenario {scenario_id} must have one positive scenario weight"
            )

        p_pv.append(frame["p_pv_mw"].to_numpy(dtype=float))
        lambda_da.append(
            frame["da_price_eur_mwh"].to_numpy(dtype=float)
        )
        raw_weights.append(float(weights[0]))

    raw_weights = np.asarray(raw_weights, dtype=float)
    pi_s = raw_weights / raw_weights.sum()

    model = ScenarioDependentBESSModel(
        {
            "dt": 0.25,
            "e_nom": 10.0,
            "p_ch_max": 5.0,
            "p_dis_max": 5.0,
            "p_grid_max": 10.0,
            "eta_ch": 0.94,
            "eta_dis": 0.94,
            "soc_min": 0.10,
            "soc_max": 0.90,
            "efc_max": 2.0,
            "alpha_cvar": 0.95,
            "beta": 0.20,
            "p_pv": np.asarray(p_pv),
            "lambda_da": np.asarray(lambda_da),
            "lambda_imb": np.asarray(lambda_da),
            "pi_s": pi_s,
            "c_curtail_eur_mwh": curtail_cost,
            "max_imbalance_mw": max_imbalance,
        }
    )

    return model.solve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--n-scenarios", type=int, default=10)
    parser.add_argument("--horizon", type=int, default=96)
    parser.add_argument("--curtail-cost", type=float, default=0.0)
    parser.add_argument("--max-imbalance", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_experiment(
        args.csv,
        args.n_scenarios,
        args.horizon,
        args.curtail_cost,
        args.max_imbalance,
    )

    result["configuration"] = {
        "input_file": str(args.csv),
        "n_scenarios": args.n_scenarios,
        "horizon_steps": args.horizon,
        "dt_hours": 0.25,
        "curtail_cost_eur_mwh": args.curtail_cost,
        "max_imbalance_mw": args.max_imbalance,
        "imbalance_price_assumption": "lambda_imb = lambda_da (diagnostic only)",
        "pv_data_note": (
            "SMARD national PV actual and day-ahead forecast, "
            "jointly sampled and peak-normalized to a hypothetical 10 MW proxy; "
            "not local plant data"
        ),
        "scenario_method": "Joint moving-block bootstrap",
        "perfect_foresight": True,
        "interpretation": (
            "Diagnostic stochastic optimization result, not a validated "
            "operational or out-of-sample performance estimate"
        ),
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

    print(json.dumps({
        key: result[key]
        for key in (
            "expected_pnl",
            "cvar",
            "objective",
            "termination_condition",
            "solve_time",
        )
    }, indent=2))

    print("\nInput:", args.csv)
    print("Scenarios:", args.n_scenarios)
    print("Horizon:", args.horizon)
    print("Imbalance assumption: lambda_imb = lambda_da (diagnostic only)")


if __name__ == "__main__":
    main()
