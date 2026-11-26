<!-- HISTORICAL CONTENT: parts of this document describe an earlier implementation. The current Phase 2.1 implementation, results and limitations are documented in docs/PHASE_2_1_CLOSURE.md. -->

<div align="center">

# Stochastic MILP Optimization for Co-Located PV-BESS Assets
### Managing Imbalance Tail Risks via CVaR and Piecewise Degradation in the German Power Market

[![SSRN Working Paper](https://img.shields.io/badge/SSRN-Preprint%207345918-blue.svg)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0007--7867--0599-A6CE39.svg)](https://orcid.org/0009-0007-7867-0599)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

**Author:** Mohammadreza (Max) Refaei  
*SRH Berlin University of Applied Sciences • Berlin, Germany*  
[`LinkedIn`](https://www.linkedin.com/in/mohammadrezarefaei/) • [`GitHub`](https://github.com/Mohammadrezarefaei) • [`SSRN`](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)

---

</div>

## 📌 Executive Summary

Co-located Solar Photovoltaic (PV) and Battery Energy Storage Systems (BESS) face acute financial exposure in deregulated wholesale power markets due to high forecast uncertainty and volatile real-time imbalance settlement mechanisms (such as the German **reBAP** single/dual-pricing framework). 

This repository implements a **single-stage, scenario-based mixed-integer linear program (MILP) with a CVaR term** for the day-ahead nomination of a co-located PV-BESS plant. All battery decisions are here-and-now: scenarios enter only through the imbalance price, there are no recourse decisions, and PV generation is deterministic. The model addresses:
* **Degradation cost:** piecewise-linear segments are defined, but with the default parameters only the first segment is reachable, so the cost is effectively a flat EUR/MWh on discharged energy. It is not a depth-of-discharge model. A cap on discharged energy per rated energy (EFC) is enforced.
* **Financial tail risk:** $\text{CVaR}_\alpha$ at $\alpha = 0.95$ on scenario profit. With few equiprobable scenarios (for example 5) this equals the worst scenario.

---

## 📐 Mathematical Formulation

### 1. Objective Function
The multi-objective function maximizes expected net revenue across all scenarios $\omega \in \Omega$ weighted by probabilities $\pi_\omega$, while penalizing battery degradation and managing tail risk through $\text{CVaR}_\alpha$:

$$\max \; (1-\beta)\left[\sum_{t=1}^T \lambda_t^{\text{DA}} P_t^{\text{DA}} \Delta t + \sum_{\omega \in \Omega} \pi_\omega \sum_{t=1}^T \lambda_{t,\omega}^{\text{imb}} \Delta P_{t,\omega} \Delta t - C_{\text{deg}}\right] + \beta \left( \zeta - \frac{1}{1-\alpha} \sum_{\omega \in \Omega} \pi_\omega z_\omega \right)$$

Where:
* $P_t^{\text{DA}}$: First-stage Day-Ahead nomination (MW)
* $\lambda_t^{\text{DA}}$: Day-Ahead market clearing price (€/MWh)
* $\lambda_{t,\omega}^{\text{imb}}$: Scenario-dependent real-time imbalance settlement price (`reBAP`) (€/MWh)
* $\Delta P_{t,\omega}$: Physical delivery mismatch $(\Delta P_{t,\omega} = P_{t,\omega}^{\text{grid}} - P_t^{\text{DA}})$
* $\zeta$: Value-at-Risk threshold ($\text{VaR}_\alpha$)
* $z_\omega$: Scenario tail loss auxiliary shortfall variable ($z_\omega \ge 0$)
* $\beta \in [0, 1]$: Risk-aversion tuning parameter
* $|\Delta P_{t,\omega}| \le \Delta_{\max}$: bound on imbalance volume (`max_imbalance_mw`, default 1.0 MW, a placeholder to be calibrated to PV forecast error)

---

### 2. Tail Risk Constraints ($\text{CVaR}_\alpha$)

For each scenario $\omega \in \Omega$:

$$z_\omega \ge \zeta - \mathcal{R}_\omega, \quad \forall \omega \in \Omega$$

$$z_\omega \ge 0, \quad \forall \omega \in \Omega$$

$$\text{CVaR}_\alpha = \zeta - \frac{1}{1-\alpha} \sum_{\omega \in \Omega} \pi_\omega z_\omega$$

---

### 3. Piecewise Linear Battery Degradation

$$C_{\text{deg}} = \sum_{t=1}^T \sum_{k=1}^K c_k \cdot \delta_{t,k}$$

$$P_{t}^{\text{dis}} \Delta t = \sum_{k=1}^K \delta_{t,k}, \quad 0 \le \delta_{t,k} \le \overline{\Delta}_k$$

$$\sum_{t=1}^T \frac{P_{t}^{\text{dis}} \Delta t}{E_{\text{rated}}} \le \text{EFC}_{\max}$$

---

## Status and limitations

* **Single-stage:** all battery variables (charge, discharge, SoC) and the day-ahead nomination are
  first-stage decisions. Only the imbalance price is scenario-dependent; there is no recourse.
* **Imbalance volume is bounded** by `max_imbalance_mw` (default 1.0 MW, a placeholder that must be
  calibrated to PV forecast error). Without such a bound the day-ahead nomination became a free
  speculative position unrelated to physical delivery.
* **Synthetic data:** day-ahead and imbalance prices in the notebook are synthetic. Real data in this
  repository is limited to one PV day and 11 days of day-ahead prices that do not overlap (see
  `DATA_SOURCES.md`). No imbalance-price (reBAP) data are used yet.
* **Few scenarios:** the examples use 5 scenarios, so CVaR at 95 % equals the worst scenario.
* **P2 diagnostic MVP:** `ScenarioDependentBESSModel` adds scenario-dependent PV, battery
  operation, curtailment, grid delivery and profit with explicit weighted lower-tail CVaR.
  Its P2 experiments use the DA price as a temporary imbalance-price proxy and perfect-foresight
  recourse. They are diagnostic only; no real reBAP series or local PV forecast is used.
* **No benchmark table:** an earlier table of profit and CVaR figures was removed because it could not
  be reproduced from this repository.
* **Tests:** `python -m pytest tests/` runs model and data-integrity tests. There is no CI yet.
* **Working paper:** the PDF below was written before these corrections and still describes a
  two-stage model and empirical backtesting. Treat it as superseded until it is revised.
---

## 📄 Working Paper & Full-Text

* **SSRN Abstract:** [SSRN ID 7345918](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)
* **Preprint PDF:** Included in this repository as [`paper_ssrn_clean.pdf`](paper_ssrn_clean.pdf)

---

Title: Stochastic MILP Optimization for Co-Located PV-BESS Assets: Managing Imbalance Tail Risks via CVaR and Piecewise Degradation in the German Power Market

Author: Mohammadreza Refaei

Venue: SSRN preprint (2026), not peer-reviewed

SSRN ID: 7345918

Link: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918

Author Contact
Mohammadreza (Max) Refaei

Institution: SRH Berlin University of Applied Sciences

ORCID: 0009-0007-7867-0599

Email: maxrefaei@proton.me
