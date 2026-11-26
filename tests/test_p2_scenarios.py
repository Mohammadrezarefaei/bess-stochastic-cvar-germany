from pathlib import Path

import pandas as pd

from src.smard_scenarios import generate_scenarios


def test_synthetic_scenario_generation_shape():
    df = generate_scenarios(n_scenarios=3, horizon_steps=96, block_length=24, seed=11)
    assert len(df) == 288
    assert df["scenario_id"].nunique() == 3
    assert df.groupby("scenario_id").size().to_dict() == {0: 96, 1: 96, 2: 96}
    assert df["scenario_weight"].eq(1.0 / 3.0).all()
    assert (df["pv_actual_mwh_15min"] >= 0).all()


def test_processed_scenario_csv_exists_with_historical_shape():
    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "processed"
        / "hybrid_scenarios_10mw_v1.csv"
    )
    assert path.exists()
    df = pd.read_csv(path)
    assert len(df) == 67200
    assert df["scenario_id"].nunique() == 100
    assert df.groupby("scenario_id").size().to_dict() == {
        scenario_id: 672 for scenario_id in range(100)
    }
