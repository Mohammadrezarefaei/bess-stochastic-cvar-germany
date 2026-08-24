# Stochastic MILP Optimization for Co-Located PV-BESS Assets

[![SSRN Working Paper](https://img.shields.io/badge/SSRN-Abstract%207345918-blue.svg)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0007--7867--0599-green.svg)](https://orcid.org/0009-0007-7867-0599)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Solver: HiGHS / CBC](https://img.shields.io/badge/solver-HiGHS%20%7C%20CBC-orange.svg)](https://highs.dev/)

A production-grade, two-stage Stochastic Mixed-Integer Linear Programming (MILP) framework for day-ahead nomination and real-time dispatch of co-located Solar Photovoltaic (PV) and Battery Energy Storage Systems (BESS) in the German power market (reBAP balancing mechanism).

---

## 📄 Technical Working Paper

The methodology, mathematical formulation, and empirical benchmarks are documented in the accompanying working paper:

> **Refaei, M.** (2026). *Stochastic MILP Optimization for Co-Located PV-BESS Assets: Managing Imbalance Tail Risks via CVaR and Piecewise Degradation in the German Power Market*. SSRN Working Paper Series, Abstract ID: [7345918](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918).

### Key Features
* **Two-Stage Stochastic MILP Formulation:** First-stage day-ahead schedule commitment; second-stage scenario-based real-time re-dispatch under renewable generation and price uncertainties.
* **Tail-Risk Hedging via CVaR:** Integrates Conditional Value-at-Risk ($\text{CVaR}_\alpha$, $\alpha = 0.95$) into the objective function to constrain adverse financial exposure from extreme imbalance settlement prices (`reBAP`).
* **Nonlinear Cell Degradation Approximation:** Incorporates piecewise linear Depth-of-Discharge (DoD) degradation costs constrained by manufacturer Equivalent Full Cycle (EFC) warranty boundaries.
* **Empirical Validation:** Backtested using real-world open data from the German Federal Network Agency ([SMARD](https://www.smard.de/)).

---

## 📁 Repository Structure

```text
├── data/                       # Historical SMARD generation and price series
├── src/
│   ├── model.py                # Pyomo Stochastic MILP optimization formulation
│   ├── cvar.py                 # Risk metric auxiliary constraints
│   ├── degradation.py         # Piecewise DoD & cycle tracking formulation
│   └── pipeline.py             # Data fetching and post-processing routines
├── notebooks/                  # Interactive benchmarks and visualization
├── docs/                       # Working paper LaTeX sources and artifacts
│   └── paper_ssrn_clean.pdf    # Full-text PDF preprint
├── requirements.txt            # Python dependencies
└── README.md
