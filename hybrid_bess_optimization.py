import numpy as np
import pandas as pd
import pyomo.environ as pyo
import matplotlib.pyplot as plt


def _extract_best_objective_bound(problem_info, objective_sense):
    """Extract the dual bound from Pyomo legacy SolverResults."""
    if problem_info is None:
        return None

    attribute = (
        "upper_bound"
        if objective_sense == pyo.maximize
        else "lower_bound"
    )
    raw_bound = getattr(problem_info, attribute, None)

    try:
        return float(pyo.value(raw_bound))
    except (TypeError, ValueError):
        return None


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
        self.max_imb = float(config.get("max_imbalance_mw", 1.0))
        if not np.isfinite(self.max_imb) or self.max_imb < 0:
            raise ValueError("max_imbalance_mw must be finite and non-negative")
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
        m.p_imb = pyo.Var(m.T, m.S, bounds=(-self.max_imb, self.max_imb))
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
        exp_profit = sum(self.pi_s[s] * m.profit_s[s] for s in m.S)
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


def weighted_lower_tail_cvar(profits, probabilities, alpha):
    """Independent weighted lower-tail profit CVaR diagnostic."""
    profits = np.asarray(profits, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)
    if profits.ndim != 1 or len(profits) != len(probabilities):
        raise ValueError("profits and probabilities must be equal-length vectors")
    if probabilities.shape != profits.shape or np.any(probabilities < 0):
        raise ValueError("scenario weights must be nonnegative")
    if not np.isclose(probabilities.sum(), 1.0):
        raise ValueError("scenario probabilities must sum to one")
    if not 0.0 < float(alpha) < 1.0:
        raise ValueError("alpha_cvar must be strictly between zero and one")

    tail_mass = 1.0 - float(alpha)
    remaining = tail_mass
    tail_value = 0.0
    for index in np.argsort(profits, kind="stable"):
        weight = float(probabilities[index])
        take = min(weight, remaining)
        tail_value += take * float(profits[index])
        remaining -= take
        if remaining <= 1e-12:
            break
    if remaining > 1e-10:
        raise ValueError("probabilities cannot cover the lower-tail mass")
    return tail_value / tail_mass


class ScenarioDependentBESSModel:
    """P2 diagnostic model with perfect-foresight scenario recourse."""

    def __init__(self, config: dict):
        self.dt = float(config.get("dt", 0.25))
        self.e_nom = float(config.get("e_nom", 10.0))
        self.p_ch_max = float(config.get("p_ch_max", 5.0))
        self.p_dis_max = float(config.get("p_dis_max", 5.0))
        self.p_grid_max = float(config.get("p_grid_max", 10.0))
        self.eta_ch = float(config.get("eta_ch", 0.94))
        self.eta_dis = float(config.get("eta_dis", 0.94))
        self.soc_min = float(config.get("soc_min", 0.10))
        self.soc_max = float(config.get("soc_max", 0.90))
        self.efc_max = float(config.get("efc_max", 2.0))
        self.alpha_cvar = float(config.get("alpha_cvar", 0.95))
        self.beta = float(config.get("beta", 0.20))
        self.c_curtail = float(config.get("c_curtail_eur_mwh", 0.0))
        self.max_imbalance_mw = float(config.get("max_imbalance_mw", 1.0))

        if not np.isfinite(self.dt) or self.dt <= 0:
            raise ValueError("dt must be finite and positive")
        if not np.isfinite(self.c_curtail) or self.c_curtail < 0:
            raise ValueError("c_curtail_eur_mwh must be finite and non-negative")
        if not np.isfinite(self.max_imbalance_mw) or self.max_imbalance_mw < 0:
            raise ValueError("max_imbalance_mw must be finite and non-negative")
        if not 0.0 < self.alpha_cvar < 1.0:
            raise ValueError("alpha_cvar must be strictly between zero and one")
        if not 0.0 <= self.beta <= 1.0:
            raise ValueError("beta must be within [0, 1]")

        self.pi_s = np.asarray(config["pi_s"], dtype=float)
        if np.any(self.pi_s < 0) or not np.isfinite(self.pi_s).all():
            raise ValueError("scenario weights must be nonnegative")
        if not np.isclose(self.pi_s.sum(), 1.0):
            raise ValueError("scenario probabilities must sum to one")

        self.S = len(self.pi_s)
        pv = np.asarray(config["p_pv"], dtype=float)
        if pv.ndim == 1:
            pv = np.repeat(pv[np.newaxis, :], self.S, axis=0)
        if pv.shape[0] != self.S:
            raise ValueError("p_pv scenario dimension must match pi_s")
        self.p_pv = pv
        self.T = pv.shape[1]

        lda = np.asarray(config["lambda_da"], dtype=float)
        if lda.ndim == 1:
            lda = np.repeat(lda[np.newaxis, :], self.S, axis=0)
        if lda.shape != (self.S, self.T):
            raise ValueError("lambda_da must have shape (S, T)")
        self.lambda_da = lda

        limb = np.asarray(config["lambda_imb"], dtype=float)
        if limb.ndim == 1:
            limb = np.repeat(limb[np.newaxis, :], self.S, axis=0)
        if limb.shape != (self.S, self.T):
            raise ValueError("lambda_imb must have shape (S, T)")
        self.lambda_imb = limb

        self.c_deg = np.asarray(
            config.get("c_deg", [15.0, 30.0, 60.0]), dtype=float
        )
        self.e_deg_cap = np.asarray(
            config.get(
                "e_deg_cap",
                [
                    0.4 * self.e_nom * self.efc_max,
                    0.4 * self.e_nom * self.efc_max,
                    0.2 * self.e_nom * self.efc_max,
                ],
            ),
            dtype=float,
        )
        if len(self.c_deg) != len(self.e_deg_cap):
            raise ValueError("degradation cost and capacity vectors must match")
        self.K = len(self.c_deg)

    def build_model(self) -> pyo.ConcreteModel:
        m = pyo.ConcreteModel(name="Scenario_Dependent_P2_BESS")
        m.T = pyo.Set(initialize=range(self.T))
        m.S = pyo.Set(initialize=range(self.S))
        m.K = pyo.Set(initialize=range(self.K))

        m.p_da = pyo.Var(m.T, bounds=(0, self.p_grid_max))
        m.p_ch = pyo.Var(m.T, m.S, bounds=(0, self.p_ch_max))
        m.p_dis = pyo.Var(m.T, m.S, bounds=(0, self.p_dis_max))
        m.u_ch = pyo.Var(m.T, m.S, within=pyo.Binary)
        m.u_dis = pyo.Var(m.T, m.S, within=pyo.Binary)
        m.soc = pyo.Var(
            m.T, m.S,
            bounds=(self.soc_min * self.e_nom, self.soc_max * self.e_nom),
        )
        m.e_seg = pyo.Var(m.T, m.S, m.K, bounds=(0, None))
        m.p_curtail = pyo.Var(m.T, m.S, bounds=(0, None))
        m.p_grid = pyo.Var(m.T, m.S, bounds=(0, self.p_grid_max))
        m.p_imb = pyo.Var(
            m.T, m.S,
            bounds=(-self.max_imbalance_mw, self.max_imbalance_mw),
        )
        m.profit_s = pyo.Var(m.S)
        m.zeta = pyo.Var()
        m.z = pyo.Var(m.S, bounds=(0, None))

        m.bin_excl = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                model.u_ch[t, s] + model.u_dis[t, s] <= 1,
        )
        m.ch_limit = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                model.p_ch[t, s] <= self.p_ch_max * model.u_ch[t, s],
        )
        m.dis_limit = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                model.p_dis[t, s] <= self.p_dis_max * model.u_dis[t, s],
        )

        def soc_rule(model, t, s):
            soc_prev = (
                self.soc_min * self.e_nom
                if t == 0
                else model.soc[t - 1, s]
            )
            return model.soc[t, s] == soc_prev + (
                self.eta_ch * model.p_ch[t, s]
                - model.p_dis[t, s] / self.eta_dis
            ) * self.dt
        m.soc_dyn = pyo.Constraint(m.T, m.S, rule=soc_rule)

        m.deg_split = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                sum(model.e_seg[t, s, k] for k in model.K)
                == model.p_dis[t, s] * self.dt,
        )
        m.deg_cap = pyo.Constraint(
            m.S, m.K,
            rule=lambda model, s, k:
                sum(model.e_seg[t, s, k] for t in model.T)
                <= self.e_deg_cap[k],
        )
        m.efc_limit = pyo.Constraint(
            m.S,
            rule=lambda model, s:
                sum(model.p_dis[t, s] * self.dt for t in model.T)
                / self.e_nom <= self.efc_max,
        )
        m.curtail_limit = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                model.p_curtail[t, s] <= self.p_pv[s, t],
        )
        m.grid_balance = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                model.p_grid[t, s]
                == self.p_pv[s, t] - model.p_curtail[t, s]
                + model.p_dis[t, s] - model.p_ch[t, s],
        )
        m.imb_calc = pyo.Constraint(
            m.T, m.S,
            rule=lambda model, t, s:
                model.p_imb[t, s]
                == model.p_grid[t, s] - model.p_da[t],
        )

        def profit_rule(model, s):
            da_revenue = sum(
                self.lambda_da[s, t] * model.p_da[t] * self.dt
                for t in model.T
            )
            imbalance = sum(
                self.lambda_imb[s, t] * model.p_imb[t, s] * self.dt
                for t in model.T
            )
            degradation = sum(
                self.c_deg[k] * model.e_seg[t, s, k]
                for t in model.T for k in model.K
            )
            curtailment = sum(
                self.c_curtail * model.p_curtail[t, s] * self.dt
                for t in model.T
            )
            return model.profit_s[s] == (
                da_revenue + imbalance - degradation - curtailment
            )
        m.profit_def = pyo.Constraint(m.S, rule=profit_rule)

        m.cvar_loss = pyo.Constraint(
            m.S,
            rule=lambda model, s:
                model.z[s] >= model.zeta - model.profit_s[s],
        )
        expected_profit = sum(
            self.pi_s[s] * m.profit_s[s] for s in m.S
        )
        cvar = m.zeta - (
            1.0 / (1.0 - self.alpha_cvar)
        ) * sum(self.pi_s[s] * m.z[s] for s in m.S)
        m.obj = pyo.Objective(
            expr=(1.0 - self.beta) * expected_profit + self.beta * cvar,
            sense=pyo.maximize,
        )
        return m

    def solve(self, solver_name: str = "appsi_highs"):
        import time

        model = self.build_model()
        solver = pyo.SolverFactory(solver_name)

        if not solver.available(exception_flag=False):
            raise RuntimeError(f"Solver '{solver_name}' is not available")

        print("Starting solver:", solver_name, flush=True)
        start_time = time.perf_counter()

        results = solver.solve(
            model,
            tee=True,
            load_solutions=False,
            options={
                "time_limit": 120,
                "random_seed": 42,
                "threads": 1,
                "mip_rel_gap": 0.05,
            },
        )

        solve_time = time.perf_counter() - start_time
        termination = results.solver.termination_condition
        solution_count = len(results.solution)

        print("Termination:", termination, flush=True)
        print("Available solutions:", solution_count, flush=True)

        if solution_count == 0:
            raise RuntimeError(
                f"No feasible solution found. Termination={termination}"
            )

        model.solutions.load_from(results)

        objective_value = float(pyo.value(model.obj))

        if termination == pyo.TerminationCondition.optimal:
            classification = "optimal"
        elif termination == pyo.TerminationCondition.maxTimeLimit:
            classification = "time_limit_feasible"
        else:
            classification = "feasible_nonoptimal"

        problem_info = results.problem[0] if len(results.problem) else None
        best_bound = _extract_best_objective_bound(
            problem_info, model.obj.sense
        )

        mip_gap = (
            abs(best_bound - objective_value)
            / max(abs(objective_value), 1e-10)
            if best_bound is not None
            else None
        )

        solver_info = results.solver
        reported_time_raw = solver_info.get("Wallclock time", solve_time)

        try:
            reported_time = float(pyo.value(reported_time_raw))
        except (TypeError, ValueError):
            reported_time = solve_time

        print("Result classification:", classification, flush=True)
        print("Loaded objective:", objective_value, flush=True)
        print("Best objective bound:", best_bound, flush=True)
        print(
            "MIP gap (%):",
            None if mip_gap is None else mip_gap * 100,
            flush=True,
        )

        scenario_profit = [
            float(pyo.value(model.profit_s[s])) for s in model.S
        ]

        expected_profit = float(
            sum(self.pi_s[s] * scenario_profit[s] for s in range(self.S))
        )

        cvar = float(pyo.value(model.zeta)) - (
            1.0 / (1.0 - self.alpha_cvar)
        ) * float(sum(
            self.pi_s[s] * pyo.value(model.z[s]) for s in model.S
        ))

        return {
            "termination_condition": str(termination),
            "result_classification": classification,
            "solver_status": str(solver_info.status),
            "solve_time": reported_time if reported_time > 0 else float(solve_time),
            "best_feasible_objective": objective_value,
            "best_objective_bound": best_bound,
            "mip_gap": mip_gap,
            "mip_gap_pct": None if mip_gap is None else mip_gap * 100,
            "p_da": [float(pyo.value(model.p_da[t])) for t in model.T],
            "p_ch": [
                [float(pyo.value(model.p_ch[t, s])) for t in model.T]
                for s in model.S
            ],
            "p_dis": [
                [float(pyo.value(model.p_dis[t, s])) for t in model.T]
                for s in model.S
            ],
            "soc": [
                [float(pyo.value(model.soc[t, s])) for t in model.T]
                for s in model.S
            ],
            "p_grid": [
                [float(pyo.value(model.p_grid[t, s])) for t in model.T]
                for s in model.S
            ],
            "p_imb": [
                [float(pyo.value(model.p_imb[t, s])) for t in model.T]
                for s in model.S
            ],
            "p_curtail": [
                [float(pyo.value(model.p_curtail[t, s])) for t in model.T]
                for s in model.S
            ],
            "scenario_profit": scenario_profit,
            "expected_pnl": expected_profit,
            "cvar": cvar,
            "objective": objective_value,
            "zeta": float(pyo.value(model.zeta)),
            "z": [float(pyo.value(model.z[s])) for s in model.S],
            "independent_weighted_cvar": weighted_lower_tail_cvar(
                scenario_profit, self.pi_s, self.alpha_cvar
            ),
        }
