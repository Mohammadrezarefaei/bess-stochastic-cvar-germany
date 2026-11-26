# Data sources and provenance

## Files

### data/raw/day_ahead_prices.csv
- Content: day-ahead prices, Germany/Luxembourg bidding zone and neighbours, EUR/MWh.
- Resolution and period: 15 minutes, 1056 rows, 2026-08-18 00:00 to 2026-08-28 23:45 (11 days).
- Format: semicolon separator, UTF-8 with BOM, dates like "Aug 18, 2026 12:00 AM".
- Timezone: the timestamp strings have no UTC offset. Timezone semantics are unknown;
  do not interpret them as UTC or local time without source documentation.
- Integrity: md5 af28dd88716d7972e88c7f3fb8b31051 (checked by tests/test_data_files.py).
- Original file name as downloaded: Day-ahead_prices_202608180000_202608290000_Quarterhour.csv
  (renamed in this repository).
- Source: SMARD. Exact page URL: TODO (fill in).
- Download date: TODO (fill in).
- Terms of use / licence: TODO (not checked).

### data/pv_profile_10mw_2026-08-06_15min.csv
- Content: one day (2026-08-06), 96 quarter-hours.
- Columns: timestamp, pv_national_mw, p_pv_mw, interval_hours.
- p_pv_mw = pv_national_mw * 10 / max(pv_national_mw); the maximum of pv_national_mw is
  41305.71 (unit as in the source file, not verified). This is a peak-normalised national
  profile scaled to a hypothetical 10 MW plant, not a measured plant output.
- Timestamp strings have no UTC offset; timezone semantics are unknown.
- Raw source file and derivation script: not in this repository. TODO (add them).
- Source and terms of use: TODO.

## Known limitations
- The price period (18-28 Aug 2026) and the PV day (6 Aug 2026) do not overlap, so
  PV and prices cannot be aligned.
- 11 days of prices and 1 day of PV are far too little to estimate a joint distribution.
- No PV forecast: forecast errors cannot be computed.
- No imbalance prices (reBAP): imbalance risk is still synthetic in the model.
- `data/processed/hybrid_scenarios_10mw_v1.csv` is synthetic: it repeats the PV profile,
  adds generated clipped noise, and independently samples DA price blocks. Its PV
  forecast/actual/error labels are not empirical observations and do not support a joint
  dependence claim. Scenario source timestamps are stored as timezone-naive
  `source_da_timestamp` values; they are not UTC or the scenario's 15-minute clock.
- See [`docs/P2_DATA_ASSESSMENT.md`](docs/P2_DATA_ASSESSMENT.md) and
  `data/processed/data_inventory.json` for the file-level inventory and integrity checks.

## Still to acquire
- Multi-month (ideally one year) day-ahead prices, realised PV and PV day-ahead forecast
  for the same period, and reBAP for the same period.
