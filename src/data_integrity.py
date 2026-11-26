"""Timestamp and unit validation helpers for repository data."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def parse_timestamps(
    values: Iterable[object],
    *,
    timestamp_format: str | None = None,
    source_timezone: str | None = None,
    to_utc: bool = False,
) -> pd.Series:
    """Parse timestamps without inferring a timezone for naïve source values.

    Explicit offsets are retained unless ``to_utc`` is requested. Naïve values
    remain naïve unless the caller supplies the source timezone. Localization
    raises for ambiguous or nonexistent daylight-saving wall times.
    """
    parsed = []
    for value in values:
        if pd.isna(value):
            parsed.append(pd.NaT)
        else:
            parsed.append(pd.Timestamp(pd.to_datetime(
                value,
                format=timestamp_format,
                errors="raise",
            )))

    populated = [value for value in parsed if not pd.isna(value)]
    awareness = [
        value.tzinfo is not None and value.utcoffset() is not None
        for value in populated
    ]
    if awareness and any(awareness) and not all(awareness):
        raise ValueError("timestamp values cannot mix timezone-aware and naïve values")
    if all(awareness) and populated and source_timezone is not None:
        raise ValueError("source_timezone cannot be applied to aware timestamps")

    if populated and all(awareness):
        zones = {str(value.tzinfo) for value in populated}
        if len(zones) == 1:
            try:
                result = pd.Series(pd.DatetimeIndex(parsed))
            except (TypeError, ValueError):
                result = pd.Series(parsed, dtype=object)
        else:
            result = pd.Series(parsed, dtype=object)
        timezone_status = (
            next(iter(zones)) if len(zones) == 1 else "explicit per-value offsets"
        )
    else:
        index = pd.DatetimeIndex(parsed)
        if source_timezone is not None and populated:
            index = index.tz_localize(
                source_timezone,
                ambiguous="raise",
                nonexistent="raise",
            )
            timezone_status = source_timezone
        else:
            timezone_status = "unknown"
        result = pd.Series(index)

    if to_utc:
        if not populated or timezone_status == "unknown":
            raise ValueError(
                "cannot convert timestamps to UTC without an established timezone"
            )
        if isinstance(result.dtype, pd.DatetimeTZDtype):
            result = result.dt.tz_convert("UTC")
        else:
            result = pd.Series(
                [
                    pd.NaT if pd.isna(value) else value.tz_convert("UTC")
                    for value in result
                ],
                dtype=object,
            )
        timezone_status = "UTC (converted from established source timezone)"

    result.attrs["timezone_status"] = timezone_status
    result.attrs["source_timezone"] = source_timezone
    return result


def audit_timestamp_intervals(
    timestamps: Iterable[object],
    *,
    expected_interval: str | pd.Timedelta | None = None,
) -> dict:
    """Report missing, duplicated, out-of-order, and irregular timestamps."""
    values = list(timestamps)
    parsed = parse_timestamps(values)
    populated = [value for value in parsed if not pd.isna(value)]

    if populated:
        aware = [
            value.tzinfo is not None and value.utcoffset() is not None
            for value in populated
        ]
        if any(aware) and not all(aware):
            raise ValueError("timestamp values cannot mix timezone-aware and naïve values")
        instants = (
            pd.DatetimeIndex([value.tz_convert("UTC") for value in populated])
            if all(aware)
            else pd.DatetimeIndex(populated)
        )
        original_instants = [
            value.tz_convert("UTC") if value.tzinfo is not None else value
            for value in populated
        ]
        ordered_pairs = zip(original_instants, original_instants[1:])
        out_of_order_count = sum(right < left for left, right in ordered_pairs)
        duplicate_count = int(instants.duplicated(keep="first").sum())
        unique_sorted = pd.DatetimeIndex(sorted(set(instants)))
        minimum = unique_sorted[0]
        maximum = unique_sorted[-1]
    else:
        instants = pd.DatetimeIndex([])
        unique_sorted = instants
        out_of_order_count = 0
        duplicate_count = 0
        minimum = maximum = None

    interval = (
        None if expected_interval is None else pd.Timedelta(expected_interval)
    )
    if interval is not None and interval <= pd.Timedelta(0):
        raise ValueError("expected_interval must be positive")

    irregular_interval_count = None
    missing_interval_count = None
    if interval is not None:
        deltas = unique_sorted[1:] - unique_sorted[:-1]
        irregular_interval_count = int(sum(delta != interval for delta in deltas))
        if len(unique_sorted):
            expected_grid = pd.date_range(
                start=minimum,
                end=maximum,
                freq=interval,
            )
            missing_interval_count = int(len(expected_grid.difference(unique_sorted)))
        else:
            missing_interval_count = 0

    return {
        "count": len(values),
        "missing_value_count": sum(pd.isna(value) for value in values),
        "duplicate_count": duplicate_count,
        "out_of_order_count": int(out_of_order_count),
        "irregular_interval_count": irregular_interval_count,
        "missing_interval_count": missing_interval_count,
        "minimum": None if minimum is None else minimum.isoformat(),
        "maximum": None if maximum is None else maximum.isoformat(),
        "timezone_status": parsed.attrs["timezone_status"],
        "expected_interval": None if interval is None else str(interval),
    }


def power_to_energy_mwh(power_mw, interval_hours):
    """Convert MW over hours to MWh, rejecting non-finite inputs."""
    power = np.asarray(power_mw, dtype=float)
    duration = np.asarray(interval_hours, dtype=float)
    if not np.isfinite(power).all():
        raise ValueError("power_mw must contain only finite values")
    if not np.isfinite(duration).all() or np.any(duration <= 0):
        raise ValueError("interval_hours must contain finite positive values")
    return power * duration
