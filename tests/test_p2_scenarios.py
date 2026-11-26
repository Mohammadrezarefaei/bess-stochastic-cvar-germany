from pathlib import Path

import pandas as pd

from src import smard_scenarios
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


def test_scenario_generator_is_reproducible_for_a_fixed_seed():
    first = generate_scenarios(3, 48, 24, seed=19)
    repeated = generate_scenarios(3, 48, 24, seed=19)
    other_seed = generate_scenarios(3, 48, 24, seed=20)

    pd.testing.assert_frame_equal(first, repeated)
    assert not first.equals(other_seed)


def test_pv_forecast_is_the_same_repeated_profile_in_every_scenario():
    df = generate_scenarios(4, 192, 48, seed=19)

    assert df.groupby("step")["p_pv_forecast_mw"].nunique().max() == 1
    assert df.groupby("step")["pv_forecast_mwh_15min"].nunique().max() == 1


def test_generated_pv_errors_are_synthetic_and_independent_of_da_values(monkeypatch):
    baseline = generate_scenarios(3, 48, 24, seed=19)
    original_loader = smard_scenarios.load_da_prices

    def changed_prices():
        da = original_loader().copy()
        da["da_price_eur_mwh"] *= -3
        return da

    monkeypatch.setattr(smard_scenarios, "load_da_prices", changed_prices)
    changed = generate_scenarios(3, 48, 24, seed=19)

    assert not baseline["da_price_eur_mwh"].equals(changed["da_price_eur_mwh"])
    pd.testing.assert_series_equal(
        baseline["pv_error_mwh_15min"], changed["pv_error_mwh_15min"]
    )
    assert (baseline["pv_error_mwh_15min"] != 0).any()


def test_source_da_timestamp_is_naive_with_unknown_timezone():
    df = generate_scenarios(2, 24, 12, seed=19)
    parsed = pd.to_datetime(df["source_da_timestamp"])

    assert parsed.dt.tz is None
