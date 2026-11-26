> HISTORICAL: This assessment describes an earlier implementation. See [Phase 2.1 Closure](PHASE_2_1_CLOSURE.md) for the current pipeline, results and limitations.

# P2.1 Data and Scenario Integrity Assessment

**Branch/baseline:** `feat/p2-research-mvp`, baseline commit `8fba833`
**Assessment scope:** the named DA source CSV, the named PV profile CSV, the processed scenario CSV, and JSON files matching `data/processed/*.json` other than the inventory itself. The machine-readable inventory is [`data/processed/data_inventory.json`](../data/processed/data_inventory.json). This is a focused inventory, not recursive discovery of every possible file under `data/`; its exact scope is also recorded in the JSON.

## Decision

**Empirical joint DA-price/PV forecast-error scenario generation is not currently supported.** Do not generate or describe empirical joint scenarios from the current files. No empirical alignment table, forecast error, autocorrelation, or price-error cross-correlation has been calculated because the required aligned observations do not exist.

The existing scenario CSV is a reproducible **synthetic diagnostic dataset**. It contains sampled historical DA price blocks paired with a repeated normalized PV proxy and synthetic clipped Gaussian perturbations. Those paired rows are not empirical DA/PV observations and support no claim of empirical price–PV dependence.

## Data inventory and classification

| File | Classification | Variables and units | Coverage / resolution | Timezone and integrity |
|---|---|---|---|---|
| [`data/raw/day_ahead_prices.csv`](../data/raw/day_ahead_prices.csv) | Stored DA source file; SMARD attribution is recorded in [`DATA_SOURCES.md`](../DATA_SOURCES.md), but source URL/download date are missing and source data cannot be independently re-verified here. | Germany/Luxembourg day-ahead price in EUR/MWh per CSV header. | 1,056 quarter-hours, 18–28 Aug 2026 inclusive (start times); interval end boundary 29 Aug 00:00. | `Start date` / `End date` use `%b %d, %Y %I:%M %p`; strings are naïve. Timezone is unknown. Both timestamp columns have 0 missing, duplicate, out-of-order, irregular, or missing internal intervals. |
| [`data/pv_profile_10mw_2026-08-06_15min.csv`](../data/pv_profile_10mw_2026-08-06_15min.csv) | Stored national-profile-like values plus a derived 10 MW proxy. Raw source and derivation script are absent; whether the national series is measured, forecast, or otherwise processed is unknown. | `pv_national_mw` unit/provenance not independently verified; `p_pv_mw` is MW after peak normalization; `interval_hours` is hours. | 96 quarter-hours on 6 Aug 2026. | Naïve timestamp strings with no timezone offset; timezone unknown. 0 missing, duplicate, out-of-order, irregular, or missing internal intervals. |
| [`data/processed/hybrid_scenarios_10mw_v1.csv`](../data/processed/hybrid_scenarios_10mw_v1.csv) | Derived **synthetic** scenario data. DA blocks are sampled from the stored price series; the PV proxy is repeated and altered with generated noise. | DA price EUR/MWh; `p_pv_*_mw` MW; `*_mwh_15min` MWh per interval; scenario weight dimensionless. “Forecast”, “actual”, and “error” are synthetic labels here, not empirical observations. | 100 scenarios × 672 steps (7 days) at 15-minute steps; 67,200 rows. | Scenario `step` sequences are complete and regular in all scenarios. `source_da_timestamp` is a naïve sampled source reference with unknown timezone, not the scenario clock. |
| [`data/processed/p2_10scenario_24h.json`](../data/processed/p2_10scenario_24h.json) | Derived diagnostic optimization output, not historical market results. | EUR and MW/MWh schedules as serialized by the P2 runner. | 10 scenarios × 96 steps. | No timestamp series; its configuration labels synthetic PV, perfect foresight, and `lambda_imb = lambda_da` as diagnostic only. |
| [`data/processed/p2_100scenario_24h_curtail_0.json`](../data/processed/p2_100scenario_24h_curtail_0.json), [`data/processed/p2_100scenario_24h_curtail_5.json`](../data/processed/p2_100scenario_24h_curtail_5.json), [`data/processed/p2_100scenario_24h_curtail_15.json`](../data/processed/p2_100scenario_24h_curtail_15.json), [`data/processed/p2_100scenario_24h_curtail_30.json`](../data/processed/p2_100scenario_24h_curtail_30.json) | Derived diagnostic optimization outputs, not historical market results. | Same output units; curtailment cost setting differs by file. | Each contains 100 scenarios × 96 steps. | No timestamp series; same synthetic PV, perfect-foresight, and DA-equals-imbalance limitations. |

Per-file SHA-256 fingerprints, schemas, timestamp diagnostics, scenario counts, probability summaries, and classifications are recorded in the JSON inventory. Scenario source-reference timestamps are also checked per scenario; gaps at independently sampled DA block joins are expected. The `step` column—not the sampled source-reference timestamp—is the regular scenario clock.

### Observed source data

- The DA CSV contains a regular 15-minute sequence of Germany/Luxembourg prices for the recorded August 18–28 period. Price units are explicit in the CSV column header. The exact SMARD URL, download date, licensing terms, and timezone interpretation are not available in the repository.
- The PV CSV contains one day of values named `pv_national_mw`, but the raw origin is missing and its measurement/forecast semantics cannot be verified. Repository documentation says the `p_pv_mw` profile was derived by scaling its peak to 10 MW; this is a hypothetical normalized proxy, not a local plant measurement.

### Derived data

- `p_pv_mw` is peak-normalized from `pv_national_mw`.
- The processed scenario file resamples contiguous DA blocks, repeats the PV shape, and derives quarter-hour MWh columns from MW values using `0.25 h`.
- The five JSON experiment files are outputs of the diagnostic optimization and are not observations.

### Synthetic assumptions

- The generator uses independent pseudo-random draws to select DA block starts and to generate per-step PV perturbations. It does not pair historically observed price and PV forecast-error blocks.
- PV perturbations are normal draws with a forecast-scaled standard deviation and then clipped to `[0, 10] MW`. The clipped values are not empirical forecast errors and need not have zero mean or a Gaussian distribution.
- A fixed seed reproduces the generator output in the current environment. The generator is explicitly labelled synthetic in [`src/smard_scenarios.py`](../src/smard_scenarios.py). The generated `source_da_timestamp` field stays timezone-naïve; no UTC conversion is performed.
- `lambda_imb = lambda_da` in the experiment runner is a diagnostic settlement assumption, not measured imbalance pricing.

### Unknown or unverifiable metadata

- The DA source timestamps do not include a timezone or offset. The PV timestamps also do not include one. Neither is silently interpreted as UTC or `Europe/Berlin`.
- The origin, exact semantics, and units of the national PV values beyond their column name are not independently verified.
- No local PV asset forecast or actual generation is available.
- No German reBAP/imbalance settlement series is available.
- The current processed CSV contains synthetic forecast/actual/error fields. It contains **zero empirically supported joint PV/DA observations**.

## Alignment and joint-data feasibility

DA start times cover 18–28 Aug 2026; the PV profile covers 6 Aug 2026. Their calendar dates do not overlap, so there is no shared interval to align. Even if dates had overlapped, the PV file has neither a verified forecast nor a verified plant actual series. The generated scenario rows do not solve this deficiency: PV data are generated from the repeated proxy and independent noise, not paired empirical observations.

| Required analysis | Result |
|---|---|
| Aligned DA price and PV forecast/actual rows | Not available; empirical joint sample size is **0** |
| PV forecast error from observations | Not calculable |
| PV error temporal autocorrelation | Not calculable |
| PV error / DA price cross-correlation | Not calculable |
| Empirical joint moving-block bootstrap | Not feasible |
| Current synthetic scenario step sequence | 672 consecutive quarter-hour steps in each of 100 scenarios |
| Current scenario probabilities | 0.01 per scenario; one weight per scenario sums to approximately 1 |

The current 288-step DA block sampling preserves historical DA order within each sampled block, but stitches separately selected blocks together and has no corresponding empirical PV/error blocks. Its continuity is not joint temporal dependence.

## Timestamp integrity implementation

[`src/data_integrity.py`](../src/data_integrity.py) provides:

- Strict timestamp parsing without assigning a timezone to naïve values.
- Optional localization only when a caller supplies a source timezone; ambiguous/nonexistent daylight-saving wall times raise errors.
- Optional UTC conversion only for timezone-aware values or values localized with an explicit source timezone.
- Duplicate, out-of-order, irregular interval, missing-value, and missing-grid-interval diagnostics.
- MW × hours → MWh conversion with finite-value and positive-duration checks.

The inventory builder [`scripts/build_data_inventory.py`](../scripts/build_data_inventory.py) applies those checks to source timestamps and checks the processed scenario step grid. It records source timezone semantics as unknown where not provided. Missing-interval counts describe internal expected grid points between observed minimum and maximum; external boundary completeness cannot be inferred from these files alone.

## Minimum additional data required

To support empirical joint PV-price scenario generation:

1. DA prices and PV forecast and realized PV on the same intervals and date range; define whether PV data are site-level or a national proxy.
2. Provenance for each file, measurement/forecast meaning, units, interval convention, source timezone, and licensing.
3. A documented timestamp convention allowing unambiguous alignment across daylight-saving transitions.
4. Multi-day data at minimum for time dependence; preferably at least a full year covering relevant seasons and operating regimes.
5. Quality flags and missing-data treatment, with no synthetic replacement represented as observations.

Authentic imbalance prices, aligned with the same settlement intervals and documented settlement conventions, are additionally required for settlement economics. They are not required merely to calculate empirical DA/PV forecast-error dependence.

## Scenario generator decision and future interface

No new empirical generator is implemented in P2.1. The existing synthetic generator is retained as a separate diagnostic path and its provenance/timestamp labels are clarified. Deterministic-profile experiments should use the measured/derived PV proxy without stochastic forecast errors; any synthetic-error experiment should be a separately named mode with its assumptions in its output metadata.

A future empirical interface should accept an aligned observation table with validated columns for timestamp, DA price, PV forecast, PV actual, explicit source timezone semantics, and scenario probabilities/weights. It should validate the interval grid before sampling jointly aligned rows or blocks. A future design can expose distinct modes such as `deterministic_profile`, `empirical_joint`, and `synthetic_error_diagnostic`; only `empirical_joint` may be used for empirical dependence claims, and only when its input observations pass alignment and provenance checks.

## Validation

Focused tests cover timestamp parsing/timezone conversion, DST ambiguity, duplicate/missing/irregular intervals, MW-to-MWh conversion, source-date non-overlap, lack of observed PV forecast/actual pairs, scenario reproducibility, scenario weights, step integrity, and explicit synthetic classification.
