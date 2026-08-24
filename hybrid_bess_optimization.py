import numpy as np
import pandas as pd
import pyomo.environ as pyo
import matplotlib.pyplot as plt

class HybridBESSModel:
    def __init__(self, config: dict):
        self.dt = config.get("dt", 0.25)
        self.p_pv = np.array(config["p_pv"])
        self.lambda_da = np.array(config["lambda_da"])
        self.lambda_imb = np.array(config["lambda_imb"])
        self.pi_s = np.array(config["pi_s"])

        self.T = len(self.lambda_da)
        self.S = len(self.pi_s)

        self.p_grid_max = config.get("p_grid_max", 10.0)
        self.e_nom = config.get("e_nom", 10.0)
        self.p_ch_max = config.get("p_ch_max", 5.0)
        self.p_dis_max = config.get("p_dis_max", 5.0)
        self.eta_ch = config.get("eta_ch", 0.94)
        self.eta_dis = config.get("eta_dis", 0.94)
        self.soc_min = config.get("soc_min", 0.10)
        self.soc_max = config.get("soc_max", 0.90)
        self.efc_max = config.get("efc_max", 2.0)

        self.alpha_cvar = config.get("alpha_cvar", 0.95)
        self.beta = config.get("beta", 0.20)
        self.c_deg = config.get("c_deg", [15.0, 30.0, 60.0])
        self.e_deg_cap = config.get("e_deg_cap", [0.4 * self.e_nom, 0.4 * self.e_nom, 0.2 * self.e_nom])
        self.K = len(self.c_deg)

    def build_model(self) -> pyo.ConcreteModel:
        m = pyo.ConcreteModel(name="Hybrid_BESS_Optimization")
        m.T = pyo.Set(initialize=range(self.T))
        m.S = pyo.Set(initialize=range(self.S))
        m.K = pyo.Set(initialize=range(self.K))

        m.p_da = pyo.Var(m.T, bounds=(0, self.p_grid_max))
        m.p_ch = pyo.Var(m.T, bounds=(0, self.p_ch_max))
        m.p_dis = pyo.Var(m.T, bounds=(0, self.p_dis_max))
        m.u_ch = pyo.Var(m.T, within=pyo.Binary)
        m.u_dis = pyo.Var(m.T, within=pyo.Binary)
        m.soc = pyo.Var(m.T, bounds=(self.soc_min * self.e_nom, self.soc_max * self.e_nom))
        m.e_seg = pyo.Var(m.T, m.K, bounds=(0, None))

        m.p_grid = pyo.Var(m.T, m.S, bounds=(0, self.p_grid_max))
        m.p_imb = pyo.Var(m.T, m.S, bounds=(-self.p_grid_max, self.p_grid_max))
        m.profit_s = pyo.Var(m.S)
        m.zeta = pyo.Var()
        m.z = pyo.Var(m.S, bounds=(0, None))

        m.bin_excl = pyo.Constraint(m.T, rule=lambda model, t: model.u_ch[t] + model.u_dis[t] <= 1)
        m.ch_limit = pyo.Constraint(m.T, rule=lambda model, t: model.p_ch[t] <= self.p_ch_max * model.u_ch[t])
        m.dis_limit = pyo.Constraint(m.T, rule=lambda model, t: model.p_dis[t] <= self.p_dis_max * model.u_dis[t])

        def soc_rule(model, t):
            soc_prev = self.soc_min * self.e_nom if t == 0 else model.soc[t-1]
            return model.soc[t] == soc_prev + (self.eta_ch * model.p_ch[t] - (model.p_dis[t] / self.eta_dis)) * self.dt
        m.soc_dyn = pyo.Constraint(m.T, rule=soc_rule)

        m.deg_split = pyo.Constraint(m.T, rule=lambda model, t: sum(model.e_seg[t, k] for k in model.K) == model.p_dis[t] * self.dt)
        m.deg_cap = pyo.Constraint(m.T, m.K, rule=lambda model, t, k: model.e_seg[t, k] <= self.e_deg_cap[k])
        m.efc_limit = pyo.Constraint(rule=lambda model: sum(model.p_dis[t] * self.dt for t in model.T) / self.e_nom <= self.efc_max)
        m.grid_balance = pyo.Constraint(m.T, m.S, rule=lambda model, t, s: model.p_grid[t, s] == self.p_pv[t] + model.p_dis[t] - model.p_ch[t])
        m.imb_calc = pyo.Constraint(m.T, m.S, rule=lambda model, t, s: model.p_imb[t, s] == model.p_grid[t, s] - model.p_da[t])

        def profit_scenario_rule(model, s):
            da_rev = sum(self.lambda_da[t] * model.p_da[t] * self.dt for t in model.T)
            imb_settle = sum(self.lambda_imb[s, t] * model.p_imb[t, s] * self.dt for t in model.T)
            deg_cost = sum(self.c_deg[k] * model.e_seg[t, k] for t in model.T for k in model.K)
            return model.profit_s[s] == da_rev + imb_settle - deg_cost
        m.profit_def = pyo.Constraint(m.S, rule=profit_scenario_rule)

        m.cvar_loss = pyo.Constraint(m.S, rule=lambda model, s: model.z[s] >= model.zeta - model.profit_s[s])
        exp_profit = sum(self.pi_s[s] * model.profit_s[s] for s in m.S)
        cvar = m.zeta - (1.0 / (1.0 - self.alpha_cvar)) * sum(self.pi_s[s] * m.z[s] for s in m.S)
        m.obj = pyo.Objective(expr=(1 - self.beta) * exp_profit + self.beta * cvar, sense=pyo.maximize)
        return m

    def solve(self, solver_name: str = "appsi_highs"):
        model = self.build_model()
        solver = pyo.SolverFactory(solver_name)
        results = solver.solve(model)
        return {
            "p_da": [pyo.value(model.p_da[t]) for t in model.T],
            "p_ch": [pyo.value(model.p_ch[t]) for t in model.T],
            "p_dis": [pyo.value(model.p_dis[t]) for t in model.T],
            "soc": [pyo.value(model.soc[t]) for t in model.T],
            "expected_pnl": sum(self.pi_s[s] * pyo.value(model.profit_s[s]) for s in range(self.S))
        }
