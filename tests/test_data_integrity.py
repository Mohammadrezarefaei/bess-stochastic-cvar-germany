import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data_integrity import (
    audit_timestamp_intervals,
    parse_timestamps,
    power_to_energy_mwh,
)


ROOT = Path(__file__).resolve().parents[1]


def test_naive_timestamps_remain_timezone_unknown_and_cannot_be_converted():
    parsed = parse_timestamps(["2026-08-06 12:00", "2026-08-06 12:15"])

    assert parsed.dt.tz is None
    assert parsed.attrs["timezone_status"] == "unknown"
    with pytest.raises(ValueError, match="without an established timezone"):
        parse_timestamps(["2026-08-06 12:00"], to_utc=True)


def test_source_style_timestamp_format_parses_without_timezone_assumption():
    parsed = parse_timestamps(
        ["Aug 18, 2026 12:00 AM"],
        timestamp_format="%b %d, %Y %I:%M %p",
    )

    assert parsed.iloc[0] == pd.Timestamp("2026-08-18 00:00:00")
    assert parsed.attrs["timezone_status"] == "unknown"


def test_known_timezone_is_preserved_and_can_be_converted_explicitly():
    source = parse_timestamps(
        ["2026-08-06 12:00", "2026-08-06 12:15"],
        source_timezone="Europe/Berlin",
    )
    utc = parse_timestamps(
        ["2026-08-06 12:00"],
        source_timezone="Europe/Berlin",
        to_utc=True,
    )

    assert str(source.dt.tz) == "Europe/Berlin"
    assert source.iloc[0].hour == 12
    assert utc.iloc[0].isoformat() == "2026-08-06T10:00:00+00:00"


def test_ambiguous_daylight_saving_wall_time_is_rejected():
    with pytest.raises(ValueError):
        parse_timestamps(
            ["2026-10-25 02:15"],
            source_timezone="Europe/Berlin",
        )


def test_nonexistent_daylight_saving_wall_time_is_rejected():
    with pytest.raises(ValueError):
        parse_timestamps(
            ["2026-03-29 02:15"],
            source_timezone="Europe/Berlin",
        )


def test_explicit_offsets_are_preserved_or_converted_to_utc():
    values = [
        "2026-08-06T12:00:00+02:00",
        "2026-08-06T12:15:00+02:00",
    ]
    preserved = parse_timestamps(values)
    utc = parse_timestamps(values, to_utc=True)

    assert preserved.iloc[0].isoformat() == "2026-08-06T12:00:00+02:00"
    assert utc.iloc[0].isoformat() == "2026-08-06T10:00:00+00:00"


def test_different_explicit_offsets_convert_to_correct_utc_instants():
    values = [
        "2026-08-06T12:00:00+02:00",
        "2026-12-06T12:00:00+01:00",
    ]

    utc = parse_timestamps(values, to_utc=True)

    assert [value.isoformat() for value in utc] == [
        "2026-08-06T10:00:00+00:00",
        "2026-12-06T11:00:00+00:00",
    ]
    assert utc.attrs["timezone_status"].startswith("UTC (converted")


def test_timestamp_audit_finds_duplicates_missing_and_irregular_intervals():
    timestamps = [
        "2026-08-06 00:00",
        "2026-08-06 00:15",
        "2026-08-06 00:15",
        "2026-08-06 01:00",
        None,
    ]
    result = audit_timestamp_intervals(
        timestamps,
        expected_interval="15min",
    )

    assert result["duplicate_count"] == 1
    assert result["missing_interval_count"] == 2
    assert result["irregular_interval_count"] == 1
    assert result["out_of_order_count"] == 0
    assert result["missing_value_count"] == 1


def test_timestamp_audit_detects_out_of_order_and_off_grid_values():
    result = audit_timestamp_intervals(
        ["2026-08-06 00:15", "2026-08-06 00:00", "2026-08-06 00:17"],
        expected_interval="15min",
    )

    assert result["out_of_order_count"] == 1
    assert result["irregular_interval_count"] == 1


def test_power_to_energy_uses_mw_times_hours_and_checks_inputs():
    result = power_to_energy_mwh(
        np.array([10.0, 4.0]),
        np.array([0.25, 0.5]),
    )

    np.testing.assert_allclose(result, [2.5, 2.0])
    with pytest.raises(ValueError, match="finite"):
        power_to_energy_mwh(float("nan"), 0.25)
    with pytest.raises(ValueError, match="positive"):
        power_to_energy_mwh(1.0, 0.0)


def test_repository_source_dates_do_not_overlap_and_pv_is_not_forecast_actual_pair():
    da = pd.read_csv(ROOT / "data" / "raw" / "day_ahead_prices.csv", sep=";", encoding="utf-8-sig")
    pv = pd.read_csv(ROOT / "data" / "pv_profile_10mw_2026-08-06_15min.csv")
    da_dates = pd.to_datetime(
        da["Start date"], format="%b %d, %Y %I:%M %p"
    ).dt.date
    pv_dates = pd.to_datetime(pv["timestamp"]).dt.date

    assert set(da_dates).isdisjoint(set(pv_dates))
    assert not any("forecast" in column or "actual" in column for column in pv.columns)


def test_current_processed_scenarios_are_explicitly_synthetic_and_weights_sum():
    inventory = json.loads(
        (ROOT / "data" / "processed" / "data_inventory.json").read_text()
    )
    scenario_record = next(
        item for item in inventory["files"]
        if item["path"] == "data/processed/hybrid_scenarios_10mw_v1.csv"
    )

    assert scenario_record["empirical_joint_observations_present"] is False
    assert scenario_record["scenario_probability"]["sum_of_one_weight_per_scenario"] == pytest.approx(1.0)
    assert scenario_record["step_integrity"]["missing_step_count"] == 0
    assert scenario_record["step_integrity"]["irregular_interval_count"] == 0


def test_inventory_reports_clean_source_grids_and_unknown_timezones():
    inventory = json.loads(
        (ROOT / "data" / "processed" / "data_inventory.json").read_text()
    )
    records = {item["path"]: item for item in inventory["files"]}

    da = records["data/raw/day_ahead_prices.csv"]
    pv = records["data/pv_profile_10mw_2026-08-06_15min.csv"]
    assert pv["timestamp_format"] == "timezone-naive timestamp string"
    assert da["start_timestamp_quality"]["timezone_status"] == "unknown"
    assert da["start_timestamp_quality"]["missing_interval_count"] == 0
    assert da["start_timestamp_quality"]["duplicate_count"] == 0
    assert pv["timestamp_quality"]["timezone_status"] == "unknown"
    assert pv["timestamp_quality"]["missing_interval_count"] == 0
    assert pv["timestamp_quality"]["duplicate_count"] == 0
    assert "arbitrary files are not recursively discovered" in inventory["inventory_scope"]
