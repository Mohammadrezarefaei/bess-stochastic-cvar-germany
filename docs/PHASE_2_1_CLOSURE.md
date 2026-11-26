# Phase 2.1 — Closure Report

**Branch:** feat/p2-research-mvp
**Date:** 2026-11-26
**Status:** Implementation and diagnostic experiment scope completed

## 1. Scope delivered

- SMARD joint 15-minute data ingestion and cleaning.
- Joint moving-block bootstrap scenario generation.
- 100 scenarios, 96 quarter-hour steps per scenario.
- Fixed seed 42, block length 96, equal scenario weights.
- Training cutoff: 2026-08-01 00:00 Europe/Berlin.
- Training observations: 29,184 rows.
- Scenario inputs: day-ahead price, national PV actual and national PV day-ahead forecast.
- PV series peak-normalized to a hypothetical 10 MW asset.
- Scenario-dependent BESS MILP with weighted lower-tail CVaR.
- Physical/model audit tests and controlled 2x2 ablation experiments.

## 2. Ablation results

All experiments use the same 100-scenario dataset and 96-step horizon.
The imbalance price is set equal to the day-ahead price as a diagnostic
assumption, not as actual German imbalance settlement.

| Degradation | Imbalance bound | Expected PnL (€) | CVaR (€) | Objective (€) | Solver result | MIP gap |
|---|---:|---:|---:|---:|---|---:|
| Old, interval-reset caps | 1 MW | 2,017.82 | 460.47 | 1,706.35 | Time limit, feasible | 0.1670% |
| New, cumulative caps | 1 MW | 2,020.03 | 459.89 | 1,708.00 | Time limit, feasible | 0.0699% |
| Old, interval-reset caps | 10 MW | 2,866.59 | 473.88 | 2,388.05 | Optimal | 0.1331% |
| New, cumulative caps | 10 MW | 2,863.37 | 473.88 | 2,385.47 | Optimal | 0.1072% |

Result files:
- `results/p2_empirical_seed42_100s.json`
- `results/p2_empirical_degnew_imb1_100s.json`
- `results/p2_empirical_degold_imb10_100s.json`
- `results/p2_empirical_revised_100s.json`

The two 1 MW runs reached the solver time limit. Their feasible incumbents
have small reported gaps, but they are not classified as proven optimal.
The two 10 MW runs terminated as optimal under the configured solver
tolerance.

## 3. Interpretation

The tested imbalance bound has a much larger effect on the objective than
the tested degradation-cap formulation. At 1 MW, changing degradation
formulation changes objective by about EUR 1.65. At 10 MW, it changes
objective by about EUR -2.58. These are results for this diagnostic setup,
not general market conclusions.

The 1 MW versus 10 MW comparison changes the feasible region and materially
changes the resulting economics. It must not be interpreted as a measured
market effect or evidence that a 10 MW imbalance limit is commercially valid.

## 4. Model and data limitations

- Imbalance prices are proxied by day-ahead prices (`lambda_imb = lambda_da`).
  No authentic German reBAP settlement series is used.
- With equal DA and imbalance prices, the direct DA nomination revenue
  coefficient cancels algebraically. The common nomination mainly couples
  scenario feasibility through the imbalance bound.
- PV actual and forecast are SMARD national series scaled to a hypothetical
  10 MW asset. They are not local plant measurements or site forecasts.
- Scenario generation is a joint historical block bootstrap, but it does not
  establish out-of-sample predictive performance.
- Scenario-dependent battery operation has perfect foresight. There are no
  nonanticipativity constraints or implementable rolling-horizon policy.
- Initial SOC is fixed at its lower bound and there is no terminal SOC target.
- Degradation costs and tranche capacities are modeling assumptions, not
  manufacturer-calibrated lifetime degradation data.
- Source timezone semantics, exact download provenance and licensing should
  be verified before external or commercial reuse.

## 5. Validation

Final test suite: `python -m pytest -q` — 48 passed.

`git diff --check` completed without reported whitespace errors.

## 6. Phase decision

Phase 2.1 is closed as an empirical-data and diagnostic stochastic
optimization MVP. This closure does not claim validated market economics,
operational performance, or out-of-sample predictive skill.

Out-of-sample validation, authentic imbalance settlement, nonanticipativity
or rolling-horizon control, terminal SOC policy, and calibrated degradation
remain future-phase work.
