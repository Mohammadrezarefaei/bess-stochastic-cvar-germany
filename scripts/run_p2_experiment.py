"""Run a diagnostic P2 scenario-dependent BESS experiment.

Imbalance prices are set equal to DA prices only as a labeled diagnostic
assumption.  This is not real German imbalance settlement data.
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


def run_experiment(csv_path: Path, n_scenarios: int, horizon: int, curtail_cost: float):
    df = pd.read_csv(csv_path)
    ids = sorted(df["scenario_id"].unique())[:n_scenarios]
    df = df[df["scenario_id"].isin(ids)].copy()

    p_pv = []
    lambda_da = []
    for scenario_id in ids:
        frame = (
            df[df["scenario_id"] == scenario_id]
            .sort_values("step")
            .iloc[:horizon]
        )
        p_pv.append(frame["p_pv_mw"].to_numpy(dtype=float))
        lambda_da.append(frame["da_price_eur_mwh"].to_numpy(dtype=float))

    pi_s = np.asarray(
        [1.0 / n_scenarios for _ in ids],
        dtype=float,
    )
    lambda_da = np.asarray(lambda_da)

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
            "lambda_da": lambda_da,
            "lambda_imb": lambda_da,
            "pi_s": pi_s,
            "c_curtail_eur_mwh": curtail_cost,
            "max_imbalance_mw": 1.0,
        }
    )
    return model.solve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data" / "processed" / "hybrid_scenarios_10mw_v1.csv",
    )
    parser.add_argument("--n-scenarios", type=int, default=10)
    parser.add_argument("--horizon", type=int, default=96)
    parser.add_argument("--curtail-cost", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_experiment(
        args.csv,
        args.n_scenarios,
        args.horizon,
        args.curtail_cost,
    )
    result["configuration"] = {
        "n_scenarios": args.n_scenarios,
        "horizon_steps": args.horizon,
        "dt_hours": 0.25,
        "curtail_cost_eur_mwh": args.curtail_cost,
        "imbalance_price_assumption": "lambda_imb = lambda_da (diagnostic only)",
        "pv_data_note": "Synthetic 10 MW peak-normalized proxy; no local forecast or forecast error",
        "perfect_foresight": True,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
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


if __name__ == "__main__":
    main()
