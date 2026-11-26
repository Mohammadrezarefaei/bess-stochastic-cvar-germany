# P2 Research MVP Audit

**Audit baseline:** branch `feat/p2-research-mvp`, commit `8fba833`  
**Baseline validation:** `python -m pytest -q` — 22 passed before audit tests were added.  
**Scope:** scenario generation and data provenance, P2 economics and physics, CVaR, input validation, and solve-result handling. No production model changes are included in this audit.

## Executive assessment

The current P2 code is a runnable diagnostic MILP, but it does not yet represent an empirically estimated joint PV/price scenario distribution or a realistic German imbalance settlement. The saved scenario CSV is reproducible from the generator, but its PV scenarios are a repeated one-day proxy with independently synthesized forecast perturbations. In the experiment runner, setting the imbalance price equal to the day-ahead price cancels the nomination's revenue coefficient exactly. The nomination then acts as a feasibility coupling variable rather than a priced market decision.

The stated power/energy units, curtailment balance, SOC recursion, binary charge/discharge exclusion, imbalance bounds, probability-weighted lower-tail CVaR, and objective signs are internally consistent subject to the limitations below. Scenario-dependent battery decisions have perfect foresight. This should remain labelled a diagnostic model until the high-priority remediation items have been resolved.

## Findings ranked by priority

### High — Scenario generation is not an empirical joint bootstrap

**Observed facts**

- `DATA_SOURCES.md` records only 11 days of DA prices and one peak-normalized PV day; the periods differ, there is no PV forecast or forecast-error series, and source provenance fields remain incomplete ([DATA_SOURCES.md](../DATA_SOURCES.md#L5-L30)).
- The generator samples DA price blocks by choosing independent starts and taking contiguous intervals within each block ([src/smard_scenarios.py](../src/smard_scenarios.py#L59-L73)). This preserves serial order inside each sampled 288-step DA block, but resets the historical path at block boundaries. It does not sample a measured joint DA/PV/error block.
- The PV forecast is the same one-day 96-step series repeated modulo 96 for every scenario ([src/smard_scenarios.py](../src/smard_scenarios.py#L60-L73)). The forecast therefore has no scenario uncertainty and repeats daily.
- At each time step, the implementation adds a new synthetic normal variate with standard deviation `max(0.05 * forecast, 0.05 MW)`, then clips actual PV to `[0, 10] MW` ([src/smard_scenarios.py](../src/smard_scenarios.py#L75-L81)). No PV forecast-error observations are loaded. The innovation is generated separately from DA price values; clipping makes the resulting error distribution censored and forecast-dependent, not a pure Gaussian error series.
- The source CSVs have naïve timestamps. The DA parser uses `Start date` without timezone localization ([src/smard_scenarios.py](../src/smard_scenarios.py#L21-L29)); the PV input also has no offset information ([DATA_SOURCES.md](../DATA_SOURCES.md#L16-L23)). The output field `source_timestamp_utc` is assigned the naïve sampled DA timestamp and serialized without an offset or `Z` ([src/smard_scenarios.py](../src/smard_scenarios.py#L84-L89)). Its UTC label is unsupported. Available files do not establish whether source wall-clock times are UTC or German local time.
- A fixed seed reproduces the generated DataFrame in this environment; a different seed changes it. The generator does not store the seed, block length, or NumPy version in the CSV itself.

**Audit tests:** [`tests/test_p2_scenarios.py`](../tests/test_p2_scenarios.py#L33-L72) checks fixed-seed reproducibility, repeated PV forecasts, synthetic PV errors being unaffected by changing DA price values, and the lack of timezone awareness in the field labelled UTC.

**Assessment:** these are exploratory synthetic scenarios, not a statistically estimated joint scenario set. The DA sampling preserves dependence only within its sampled historical blocks. There is no empirical price–PV dependence or PV forecast-error temporal dependence. Results depending on PV uncertainty or its dependence with DA prices cannot be interpreted as empirical findings.

### High — Equal DA and imbalance prices cancel the nomination revenue

The P2 scenario profit equation in [hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L288-L308) is

`Profit_s = Σ_t λ_DA[s,t] p_DA[t] Δt + Σ_t λ_imb[s,t] (p_grid[s,t] - p_DA[t]) Δt - C_deg[s] - C_curt[s]`.

The runner sets `lambda_imb` to the same matrix as `lambda_da` ([scripts/run_p2_experiment.py](../scripts/run_p2_experiment.py#L59-L64)). Substitution gives

`Profit_s = Σ_t λ_DA[s,t] p_grid[s,t] Δt - C_deg[s] - C_curt[s]`,

because the coefficient on `p_DA[t]` is `λ_DA[s,t] - λ_imb[s,t] = 0` for every scenario and interval.

Thus `p_da` has no direct economic contribution to scenario profit or CVaR in these experiments. It remains bounded to `[0, p_grid_max]` and appears in `p_imb = p_grid - p_da` with the imbalance bound ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L204-L219), [hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L281-L286)). It only couples scenario feasibility: one common nomination must be within `max_imbalance_mw` of each scenario's grid delivery. It is not being optimized as a meaningful DA revenue decision.

**Audit test:** [`tests/test_p2_audit.py`](../tests/test_p2_audit.py#L23-L40) substitutes the model's imbalance identity into the settlement equation and confirms the `p_da` coefficients cancel when the two price arrays match.

**Assessment:** no real reBAP series is present, and none should be fabricated. Current output is a diagnostic physical-delivery revenue proxy, not validated German DA/imbalance settlement economics.

### High — Scenario recourse assumes perfect foresight

`p_ch`, `p_dis`, `soc`, curtailment, grid delivery, and imbalance are indexed by both time and scenario ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L204-L220), [hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L224-L286)). There are no nonanticipativity constraints or scenario-tree information sets. Every scenario's full path therefore has its own full-horizon operation plan. The runner labels this as perfect foresight in saved experiment configuration ([scripts/run_p2_experiment.py](../scripts/run_p2_experiment.py#L89-L97)).

**Assessment:** this is a perfect-information upper bound/diagnostic recourse model, not an implementable policy. It must not be described as realistic operation.

### Medium — Degradation segments reset each interval and the default curve is effectively flat

`e_seg[t,s,k]` is constrained by `e_seg[t,s,k] <= e_deg_cap[k]` separately for every time, scenario, and segment ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L252-L268)). Capacities are therefore reapplied each interval; no cumulative-throughput constraint tracks how much of a segment has already been consumed over the horizon. The objective uses the segment-specific EUR/MWh rates on discharged MWh ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L297-L300)).

With defaults, the first segment capacity is 4 MWh, while the maximum discharge energy in one 15-minute interval is `5 MW × 0.25 h = 1.25 MWh`. Since segment 1 is the cheapest and can alone contain every interval's discharge, higher-cost segments are never needed in the default experiment. The implemented default cost is consequently €15 per discharged MWh, not an increasing lifetime-throughput degradation curve.

**Audit test:** [`tests/test_p2_audit.py`](../tests/test_p2_audit.py#L37-L56) checks that the cap is separately instantiated for every interval and scenario.

**Assessment:** whether per-interval caps were intended is a modeling decision, but they do not represent cumulative degradation tranches. The resulting effective flat rate should not be characterized as a piecewise lifetime-throughput curve.

### Medium — SOC starts at its lower bound and has no terminal target

SOC is constrained to `[soc_min * e_nom, soc_max * e_nom]`, with the first interval's predecessor fixed at `soc_min * e_nom` ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L209-L212), [hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L240-L250)). There is no terminal SOC condition after the final modeled interval. The model may end depleted at the minimum and does not value or preserve energy beyond the horizon.

**Assessment:** units and recursion are consistent (`MW × hours = MWh`; charge is multiplied by `eta_ch`, discharge divided by `eta_dis`). Initial SOC at minimum is an explicit assumption in code; lack of a terminal target creates an end-of-horizon effect. This should be specified and tested against the intended operating use case.

### Medium — Input validation is partial; non-optimal solve status is read too late

- The constructor validates `dt`, curtailment cost, imbalance limit, `alpha_cvar`, `beta`, scenario probabilities, and selected dimensions ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L128-L182)). It does not validate finite values or physical ranges for PV/price arrays, PV dimensionality beyond its leading scenario dimension, `e_nom`, power limits, efficiencies, SOC bounds, EFC, degradation costs, or degradation capacities.
- The standalone lower-tail helper validates probability shape/nonnegativity/sum and confidence level, but does not reject non-finite profits ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L97-L122)). The model-level probabilities do explicitly reject non-finite weights.
- Solver availability is checked, but termination status is not checked before reading decision and auxiliary variables ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L327-L345)). The status is only included in the eventual result dictionary ([hybrid_bess_optimization.py](../hybrid_bess_optimization.py#L346-L383)). An infeasible/non-optimal result with uninitialized variables therefore raises during extraction instead of producing an explicit status error.
- The experiment runner ignores `scenario_weight` in its CSV and assigns `1 / requested_n_scenarios` to each selected scenario ([scripts/run_p2_experiment.py](../scripts/run_p2_experiment.py#L23-L43)). This matches the generated equal weights, but silently assumes equal weights for other input files.

**Audit tests:** [`tests/test_p2_audit.py`](../tests/test_p2_audit.py#L59-L75) verifies scenario-indexed recourse, absence of nonanticipativity and terminal-SOC constraints, and the fixed initial SOC. [`tests/test_p2_audit.py`](../tests/test_p2_audit.py#L77-L87) documents acceptance of non-finite PV/price inputs; [`tests/test_p2_audit.py`](../tests/test_p2_audit.py#L89-L111) verifies that a simulated infeasible solver result reaches value extraction before status handling.

**Assessment:** the lower-tail CVaR signs and weighted-tail calculation are otherwise consistent: `z_s >= zeta - Profit_s`, `z_s >= 0`, and maximizing `zeta - E[z]/(1-alpha)` yields lower-tail profit CVaR. The helper sorts profits ascending and fractionally takes exactly `1-alpha` probability mass, which correctly handles unequal weights and a boundary scenario. The existing tests cover equal and unequal weights. Solver output extraction and malformed numeric inputs need explicit guards before results are research-ready.

### Low — Scenario and experiment artifact provenance is incomplete

The generator is deterministic for a fixed seed, but neither the CSV nor the experiment output records the seed or generator block length. `DATA_SOURCES.md` has unresolved source URL, download date, licensing, and PV derivation details ([DATA_SOURCES.md](../DATA_SOURCES.md#L5-L23)). The runner records some model settings but not the seed/source-generation configuration ([scripts/run_p2_experiment.py](../scripts/run_p2_experiment.py#L89-L100)).

**Assessment:** results can be regenerated only when the caller already knows the complete command and the dependency environment. A manifest and data provenance are needed before describing the experiment as independently reproducible.

## Physical and unit checks

| Item | Observed implementation | Audit result |
|---|---|---|
| PV curtailment | `0 <= p_curtail <= p_pv` | Correct bounds; code and solved-output test cover this. |
| Grid balance | `p_grid = p_pv - p_curtail + p_dis - p_ch` | Dimensionally consistent MW balance. |
| Grid exchange | `p_grid` has bounds `[0, p_grid_max]` | Export-only. No grid import variable; no unrestricted grid charging. |
| Charge/discharge | Binary `u_ch + u_dis <= 1` with power gating | Simultaneous charge/discharge is excluded. |
| SOC | `SOC_t = SOC_(t-1) + (eta_ch*p_ch - p_dis/eta_dis)*dt` | Correct MWh units for the stated efficiency convention; initial SOC fixed to minimum; terminal condition absent. |
| Battery limits | SOC and charge/discharge variable bounds | Enforced for provided parameter values; parameter validity is not fully checked. |
| EFC | `Σ p_dis*dt / e_nom <= efc_max` per scenario | Discharge-throughput EFC convention; this is not total charge-plus-discharge throughput. |
| Imbalance | `p_imb = p_grid - p_da`, bounded symmetrically | Consistent with the code's sign convention; commercial settlement sign remains unvalidated. |
| Degradation | Segment energy in MWh times EUR/MWh; caps indexed by interval | Units consistent, but segment capacities reset every interval and default high-cost segments are unreachable. |
| Curtailment cost | `c_curtail * p_curtail * dt` | EUR/MWh × MW × h = EUR, consistent. |

## Recommendations in priority order

1. **Replace synthetic joint-scenario claims.** Acquire aligned DA price, PV forecast, realized PV, and forecast-error data with source, resolution, timezone, and licensing provenance. Until then, label current output synthetic and do not infer empirical joint dependence.
2. **Resolve settlement inputs and timing.** Obtain authentic imbalance settlement prices and define when DA prices, nominations, PV forecasts, and recourse decisions become observable. Keep the DA-equals-imbalance case only as a clearly labelled algebraic diagnostic.
3. **Choose an information structure.** Add scenario-tree/nonanticipativity constraints or rolling-horizon re-optimization so decisions cannot depend on unobserved future scenario outcomes.
4. **Specify battery endpoint and degradation semantics.** Decide initial and terminal SOC policy, and whether degradation costs are a static per-MWh proxy or cumulative throughput tranches. Encode and test that choice explicitly.
5. **Harden model boundaries.** Validate all arrays and physical parameters for dimensionality, finiteness, and admissible ranges; use CSV scenario weights or reject unsupported nonuniform weights; reject solver results without an acceptable termination condition before extracting values.
6. **Make artifacts self-describing.** Record seed, block settings, data fingerprints, generator version, model configuration, and solver/version alongside each run. Correct or remove the unsupported `source_timestamp_utc` label unless timestamps are localized using verified source semantics.
7. **Only then interpret sensitivities.** Re-run the 10/100-scenario cases after the above changes. Current numbers are not regression targets for market economics.

## Audit test result

After adding focused audit tests, `python -m pytest -q` passes **31 tests**. These tests are diagnostic assertions of current behavior, including the identified limitations; they do not remediate those limitations.
