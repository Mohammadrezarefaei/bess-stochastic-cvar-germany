# Stochastic MILP Optimization for Co-Located PV-BESS Assets
### Managing Imbalance Tail Risks via CVaR and Piecewise Degradation in the German Power Market

[![SSRN Working Paper](https://img.shields.io/badge/SSRN-Preprint%207345918-blue.svg)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0007--7867--0599-A6CE39.svg)](https://orcid.org/0009-0007-7867-0599)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

**Author:** Mohammadreza (Max) Refaei  
**Institution:** SRH Berlin University of Applied Sciences • Berlin, Germany  
**Links:** [LinkedIn](https://www.linkedin.com/in/mohammadrezarefaei/) | [GitHub](https://github.com/Mohammadrezarefaei) | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)

---

## 📌 Executive Summary

Co-located Solar Photovoltaic (PV) and Battery Energy Storage Systems (BESS) face acute financial exposure in deregulated wholesale power markets due to high forecast uncertainty and volatile real-time imbalance settlement mechanisms (such as the German **reBAP** single/dual-pricing framework).

This repository implements a **Two-Stage Stochastic Mixed-Integer Linear Programming (MILP)** model that optimizes day-ahead market commitments while mitigating:
* **Physical Asset Degradation:** Utilizing a piecewise linear depth-of-discharge (DoD) penalty constrained by Equivalent Full Cycle (EFC) warranty ceilings.
* **Financial Tail Risk:** Incorporating **Conditional Value-at-Risk (CVaR)** at $\alpha = 0.95$ to protect cash flows against extreme imbalance settlement penalties.

---

## 📐 Mathematical Formulation

### 1. Multi-Objective Function

The model maximizes expected market revenue across scenarios $\omega \in \Omega$ while controlling cell degradation and CVaR tail loss:

$$\max_{\Xi} \sum_{t=1}^T \lambda_t^{\text{DA}} P_t^{\text{DA}} \Delta t + \sum_{\omega \in \Omega} \pi_\omega \left[ \sum_{t=1}^T \left( \lambda_{t,\omega}^{\text{imb}} \Delta P_{t,\omega} - C_{\text{deg}}(P_{t,\omega}^{\text{ch}}, P_{t,\omega}^{\text{dis}}) \right) \Delta t \right] + \beta \left( \zeta - \frac{1}{1-\alpha} \sum_{\omega \in \Omega} \pi_\omega z_\omega \right)$$

Where:
* $P_t^{\text{DA}}$: First-stage Day-Ahead nomination (MW)
* $\lambda_t^{\text{DA}}$: Day-Ahead market clearing price (€/MWh)
* $\lambda_{t,\omega}^{\text{imb}}$: Real-time imbalance settlement price (`reBAP`) (€/MWh)
* $\Delta P_{t,\omega}$: Net physical deviation $(\Delta P_{t,\omega} = P_{t,\omega}^{\text{grid}} - P_t^{\text{DA}})$
* $\zeta$: Value-at-Risk threshold ($\text{VaR}_\alpha$)
* $z_\omega$: Tail loss auxiliary shortfall variable ($z_\omega \ge 0$)
* $\beta \in [0, 1]$: Risk-aversion tuning parameter

---

### 2. Tail Risk Constraints (CVaR)

$$z_\omega \ge \zeta - \mathcal{R}_\omega, \quad \forall \omega \in \Omega$$

$$z_\omega \ge 0, \quad \forall \omega \in \Omega$$

$$\text{CVaR}_\alpha = \zeta - \frac{1}{1-\alpha} \sum_{\omega \in \Omega} \pi_\omega z_\omega$$

---

### 3. Piecewise Linear Battery Aging

$$C_{\text{deg}}(P_{t,\omega}^{\text{ch}}, P_{t,\omega}^{\text{dis}}) = \sum_{k=1}^K c_k \cdot \delta_{t,\omega,k}$$

$$P_{t,\omega}^{\text{dis}} \Delta t = \sum_{k=1}^K \delta_{t,\omega,k}, \quad 0 \le \delta_{t,\omega,k} \le \overline{\Delta}_k$$

$$\sum_{t=1}^T \frac{P_{t,\omega}^{\text{ch}} \eta_{\text{ch}} + P_{t,\omega}^{\text{dis}} / \eta_{\text{dis}}}{2 \cdot E_{\text{rated}}} \Delta t \le \text{EFC}_{\max}$$

---

## 📊 Benchmark & Performance Metrics

Backtested over historical generation profiles and real price series from the German Federal Network Agency (**SMARD / Bundesnetzagentur**):

| Dispatch Strategy | Expected Daily Profit (€) | 5% Worst-Case CVaR (€) | Daily EFC Usage | Risk Reduction |
| :--- | :---: | :---: | :---: | :---: |
| **Deterministic (No Risk Metric)** | 14,820.50 | -2,140.20 | 2.15 | Baseline |
| **Stochastic MILP ($\beta = 0.0$)** | 14,210.80 | -850.40 | 1.62 | +60.2% |
| **Risk-Averse Stochastic ($\beta = 0.5$)** | **13,940.10** | **+1,220.60** | **1.28** | **+157.0%** |
| **Conservative Hedged ($\beta = 1.0$)** | 13,100.40 | +2,450.00 | 0.94 | +214.5% |

---

## 📁 Repository Structure

```text
├── data/                       # Historical SMARD generation and reBAP price series
├── src/
│   ├── model.py                # Pyomo Stochastic MILP optimization engine
│   ├── cvar.py                 # CVaR auxiliary constraints & risk modules
│   ├── degradation.py         # Piecewise DoD & cycle wear formulation
│   └── pipeline.py             # Data fetching and post-processing routines
├── docs/                       # Working paper artifacts & preprint PDF
│   └── paper_ssrn_clean.pdf    # SSRN Working Paper full-text PDF
├── requirements.txt            # Python dependencies
└── README.md
🚀 Quickstart
1. Setup Environment
Bash
git clone [https://github.com/Mohammadrezarefaei/bess-stochastic-cvar-germany.git](https://github.com/Mohammadrezarefaei/bess-stochastic-cvar-germany.git)
cd bess-stochastic-cvar-germany
pip install -r requirements.txt
2. Execute Optimization
Python
from src.pipeline import run_stochastic_dispatch

results = run_stochastic_dispatch(
    pv_capacity_mw=10.0,
    bess_capacity_mwh=20.0,
    bess_power_mw=5.0,
    cvar_weight=0.50,
    alpha=0.95
)

print(f"Optimal Expected Profit: {results['expected_profit']:.2f} EUR")
print(f"CVaR (95% Tail Risk):     {results['cvar']:.2f} EUR")
print(f"BESS Cycling (EFC):       {results['efc_used']:.2f} Cycles")
📚 Citation
Code snippet
@article{refaei2026stochastic,
  title={Stochastic MILP Optimization for Co-Located PV-BESS Assets: Managing Imbalance Tail Risks via CVaR and Piecewise Degradation in the German Power Market},
  author={Refaei, Mohammadreza},
  journal={SSRN Electronic Journal},
  year={2026},
  doi={10.2139/ssrn.7345918},
  url={[https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7345918)}
}
👤 Author Contact
Mohammadreza (Max) Refaei

Institution: SRH Berlin University of Applied Sciences

ORCID: 0009-0007-7867-0599

Email: maxrefaei@proton.me
