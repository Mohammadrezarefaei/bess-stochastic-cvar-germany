"""Build a provenance-aware inventory of the data files in this repository."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_integrity import audit_timestamp_intervals, parse_timestamps


DA_PATH = ROOT / "data" / "raw" / "day_ahead_prices.csv"
PV_PATH = ROOT / "data" / "pv_profile_10mw_2026-08-06_15min.csv"
SCENARIO_PATH = ROOT / "data" / "processed" / "hybrid_scenarios_10mw_v1.csv"
INVENTORY_PATH = ROOT / "data" / "processed" / "data_inventory.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_metadata(path: Path, classification: str) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "classification": classification,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _inventory_da_prices() -> dict:
    frame = pd.read_csv(DA_PATH, sep=";", encoding="utf-8-sig")
    start = parse_timestamps(
        frame["Start date"],
        timestamp_format="%b %d, %Y %I:%M %p",
    )
    end = parse_timestamps(
        frame["End date"],
        timestamp_format="%b %d, %Y %I:%M %p",
    )
    price_column = next(
        column for column in frame.columns
        if column.startswith("Germany/Luxembourg")
    )
    return {
        **_file_metadata(DA_PATH, "observed source data; source attribution recorded but URL absent"),
        "source": "SMARD per DATA_SOURCES.md; exact URL and download date unknown",
        "variables": {
            "Germany/Luxembourg day-ahead price": {
                "column": price_column,
                "unit": "EUR/MWh (from column header)",
                "missing_values": int(frame[price_column].isna().sum()),
            }
        },
        "temporal_resolution": "15 minutes",
        "timestamp_fields": ["Start date", "End date"],
        "timestamp_format": "%b %d, %Y %I:%M %p",
        "timezone_semantics": "unknown; source strings are timezone-naive",
        "start_timestamp_quality": audit_timestamp_intervals(
            start, expected_interval="15min"
        ),
        "end_timestamp_quality": audit_timestamp_intervals(
            end, expected_interval="15min"
        ),
        "coverage": {
            "start": start.min().isoformat(),
            "end": end.max().isoformat(),
            "end_convention": "exclusive end boundary of the final 15-minute interval",
            "row_count": len(frame),
        },
        "units_and_source_notes": (
            "DA price unit is stated in the CSV column header. Source URL, download "
            "date, and terms are not verified in repository documentation."
        ),
    }


def _inventory_pv_profile() -> dict:
    frame = pd.read_csv(PV_PATH)
    timestamps = parse_timestamps(frame["timestamp"])
    return {
        **_file_metadata(PV_PATH, "stored source-like series plus derived proxy"),
        "source": "Underlying source and derivation script are absent; see DATA_SOURCES.md",
        "variables": {
            "pv_national_mw": {
                "unit": "MW as named; unit and provenance not independently verified",
                "classification": "stored input column; source status unknown",
                "missing_values": int(frame["pv_national_mw"].isna().sum()),
            },
            "p_pv_mw": {
                "unit": "MW",
                "classification": "derived peak-normalized 10 MW hypothetical profile",
                "derivation": "pv_national_mw * 10 / max(pv_national_mw)",
                "missing_values": int(frame["p_pv_mw"].isna().sum()),
            },
            "interval_hours": {
                "unit": "hours",
                "classification": "stored interval metadata",
                "missing_values": int(frame["interval_hours"].isna().sum()),
            },
        },
        "temporal_resolution": "15 minutes",
        "timestamp_fields": ["timestamp"],
        "timestamp_format": "timezone-naive timestamp string",
        "timezone_semantics": "unknown; timestamps contain no UTC offset",
        "timestamp_quality": audit_timestamp_intervals(
            timestamps, expected_interval="15min"
        ),
        "coverage": {
            "start": timestamps.min().isoformat(),
            "end": timestamps.max().isoformat(),
            "row_count": len(frame),
        },
        "forecast_or_actual": (
            "Neither a verified plant actual series nor a verified forecast series. "
            "The 10 MW column is a normalized national-profile proxy."
        ),
    }


def _inventory_scenarios() -> dict:
    frame = pd.read_csv(SCENARIO_PATH)
    scenario_records = []
    source_timestamp_checks = []
    expected_steps = set(range(int(frame["step"].min()), int(frame["step"].max()) + 1))
    for scenario_id, group in frame.groupby("scenario_id", sort=True):
        steps = group["step"].astype(int)
        present = set(steps)
        source_timestamp_checks.append(
            audit_timestamp_intervals(
                group.sort_values("step")["source_da_timestamp"],
                expected_interval="15min",
            )
        )
        scenario_records.append(
            {
                "scenario_id": int(scenario_id),
                "row_count": len(group),
                "duplicate_step_count": int(steps.duplicated().sum()),
                "missing_step_count": len(expected_steps - present),
                "step_min": int(steps.min()),
                "step_max": int(steps.max()),
                "step_irregular_interval_count": int(
                    (steps.sort_values().diff().dropna() != 1).sum()
                ),
                "scenario_weight": float(group["scenario_weight"].iloc[0]),
                "scenario_weight_unique_count": int(group["scenario_weight"].nunique()),
            }
        )

    return {
        **_file_metadata(
            SCENARIO_PATH,
            "derived synthetic scenarios; not empirical joint observations",
        ),
        "source": (
            "Generated by src/smard_scenarios.py from the DA file and repeated "
            "one-day PV proxy, plus synthetic clipped Gaussian perturbations"
        ),
        "temporal_resolution": "15 minutes by integer step; source timestamps are not the scenario clock",
        "horizon_steps_per_scenario": int(frame.groupby("scenario_id").size().iloc[0]),
        "scenario_count": int(frame["scenario_id"].nunique()),
        "row_count": len(frame),
        "missing_values": {
            column: int(frame[column].isna().sum())
            for column in (
                "da_price_eur_mwh",
                "pv_forecast_mwh_15min",
                "pv_actual_mwh_15min",
                "pv_error_mwh_15min",
                "p_pv_mw",
                "p_pv_forecast_mw",
                "scenario_weight",
            )
        },
        "scenario_probability": {
            "weight_column": "scenario_weight",
            "unique_weight_values": sorted(
                float(value) for value in frame["scenario_weight"].unique()
            ),
            "sum_of_one_weight_per_scenario": float(
                frame.groupby("scenario_id")["scenario_weight"].first().sum()
            ),
        },
        "step_integrity": {
            "duplicate_step_count": sum(
                item["duplicate_step_count"] for item in scenario_records
            ),
            "missing_step_count": sum(
                item["missing_step_count"] for item in scenario_records
            ),
            "irregular_interval_count": sum(
                item["step_irregular_interval_count"] for item in scenario_records
            ),
            "per_scenario": scenario_records,
        },
        "source_timestamp_field": {
            "column": "source_da_timestamp",
            "timezone_semantics": (
                "unknown; values are timezone-naive DA source timestamps"
            ),
            "interpretation": "sampled source reference, not the scenario interval timestamp",
            "per_scenario_quality": source_timestamp_checks,
            "note": (
                "Irregular gaps are expected where independently sampled DA blocks "
                "are stitched together; use step as the scenario clock."
            ),
        },
        "pv_columns": {
            "p_pv_forecast_mw": "repeated deterministic normalized proxy; not an observed forecast",
            "p_pv_mw": "generated proxy actual with synthetic perturbation; not measured actual",
            "pv_error_mwh_15min": "synthetic difference; not empirical forecast error",
        },
        "empirical_joint_observations_present": False,
        "joint_observation_reason": (
            "PV values/errors are generated independently of the sampled DA price values; "
            "the source files do not contain aligned PV forecast and actual observations."
        ),
    }


def _inventory_experiment_result(path: Path) -> dict:
    result = json.loads(path.read_text())
    return {
        **_file_metadata(path, "derived diagnostic model output"),
        "configuration": result.get("configuration", {}),
        "result_dimensions": {
            "scenario_profit_count": len(result.get("scenario_profit", [])),
            "time_steps": len(result.get("p_da", [])),
            "scenario_count": len(result.get("p_ch", [])),
        },
        "empirical_validity": False,
        "limitation": (
            "Derived from synthetic PV scenarios, perfect-foresight recourse, "
            "and the explicitly diagnostic DA-equals-imbalance price assumption."
        ),
    }


def build_inventory() -> dict:
    files = [
        _inventory_da_prices(),
        _inventory_pv_profile(),
        _inventory_scenarios(),
    ]
    experiment_paths = sorted(
        path
        for path in (ROOT / "data" / "processed").glob("*.json")
        if path != INVENTORY_PATH
    )
    files.extend(_inventory_experiment_result(path) for path in experiment_paths)

    da = files[0]["coverage"]
    pv = files[1]["coverage"]
    return {
        "schema_version": 1,
        "repository": "Mohammadrezarefaei/bess-stochastic-cvar-germany",
        "inventory_scope": (
            "Specifically inventories data/raw/day_ahead_prices.csv, "
            "data/pv_profile_10mw_2026-08-06_15min.csv, "
            "data/processed/hybrid_scenarios_10mw_v1.csv, and JSON files matching "
            "data/processed/*.json except this inventory; arbitrary files are not "
            "recursively discovered."
        ),
        "files": files,
        "joint_data_feasibility": {
            "empirical_joint_da_pv_forecast_error_dataset_available": False,
            "da_coverage": da,
            "pv_profile_coverage": pv,
            "calendar_overlap": False,
            "pv_forecast_available": False,
            "pv_actual_available": False,
            "imbalance_price_available": False,
            "minimum_additional_data": [
                "DA price series with documented source, units, resolution, and timezone",
                "PV forecast and realized PV for the same site or explicitly defined proxy",
                "Aligned interval timestamps and a documented timezone for both series",
                "Sufficient multi-day coverage for temporal dependence analysis",
                "For settlement economics, the corresponding authentic imbalance price series",
            ],
        },
    }


def main() -> None:
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory()
    INVENTORY_PATH.write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Wrote inventory for {len(inventory['files'])} data files to {INVENTORY_PATH}")


if __name__ == "__main__":
    main()
