from types import SimpleNamespace

import numpy as np
import pytest
from pyomo.repn import generate_standard_repn

import hybrid_bess_optimization
from hybrid_bess_optimization import (
    ScenarioDependentBESSModel,
    _extract_best_objective_bound,
)


def audit_config(n_scenarios=2, n_steps=16):
    pv = np.full((n_scenarios, n_steps), 2.0)
    prices = np.full((n_scenarios, n_steps), 50.0)
    return {
        "p_pv": pv,
        "lambda_da": prices,
        "lambda_imb": prices.copy(),
        "pi_s": [1.0 / n_scenarios] * n_scenarios,
        "max_imbalance_mw": 10.0,
    }


def test_equal_da_and_imbalance_prices_cancel_nomination_revenue():
    model = ScenarioDependentBESSModel(audit_config())
    pyomo_model = model.build_model()

    for scenario in pyomo_model.S:
        settlement = sum(
            model.lambda_da[scenario, t] * pyomo_model.p_da[t] * model.dt
            + model.lambda_imb[scenario, t]
            * (pyomo_model.p_grid[t, scenario] - pyomo_model.p_da[t])
            * model.dt
            for t in pyomo_model.T
        )
        repn = generate_standard_repn(settlement)
        p_da_coefficients = [
            coefficient
            for variable, coefficient in zip(repn.linear_vars, repn.linear_coefs)
            if variable.parent_component() is pyomo_model.p_da
        ]
        assert not p_da_coefficients


def test_degradation_segment_caps_are_cumulative_over_horizon():
    cfg = audit_config(n_scenarios=2, n_steps=4)
    cfg["e_deg_cap"] = [0.1, 0.2, 0.3]
    model = ScenarioDependentBESSModel(cfg)
    pyomo_model = model.build_model()

    assert len(pyomo_model.deg_cap) == model.S * model.K
    for scenario in pyomo_model.S:
        for k in pyomo_model.K:
            constraint = pyomo_model.deg_cap[scenario, k]
            repn = generate_standard_repn(constraint.body)
            assert constraint.upper() == pytest.approx(cfg["e_deg_cap"][k])
            assert repn.constant == pytest.approx(0.0)
            assert set(variable.index() for variable in repn.linear_vars) == {
                (t, scenario, k) for t in range(model.T)
            }
            assert list(repn.linear_coefs) == pytest.approx([1.0] * model.T)


def test_default_degradation_caps_match_cumulative_efc_budget():
    model = ScenarioDependentBESSModel(audit_config())
    assert model.e_deg_cap.tolist() == pytest.approx([8.0, 8.0, 4.0])


def test_scenario_recourse_has_no_nonanticipativity_or_terminal_soc_rule():
    model = ScenarioDependentBESSModel(audit_config(n_scenarios=2, n_steps=4))
    pyomo_model = model.build_model()

    assert pyomo_model.p_ch.index_set().dimen == 2
    constraint_names = {
        name.lower() for name in pyomo_model.component_map()
        if "nonant" in name.lower() or "terminal" in name.lower()
    }
    assert not constraint_names

    initial_soc_balance = pyomo_model.soc_dyn[0, 0]
    initial_repn = generate_standard_repn(initial_soc_balance.body)
    assert initial_repn.constant == pytest.approx(
        -model.soc_min * model.e_nom
    )


def test_non_finite_pv_and_price_inputs_are_not_rejected():
    cfg = audit_config(n_scenarios=2)
    cfg["p_pv"][0, 0] = np.nan
    cfg["lambda_da"] = np.asarray(cfg["lambda_da"], dtype=float)
    cfg["lambda_da"][0, 0] = np.inf

    model = ScenarioDependentBESSModel(cfg)

    assert np.isnan(model.p_pv[0, 0])
    assert np.isinf(model.lambda_da[0, 0])


def test_solver_infeasible_result_is_rejected_before_loading(monkeypatch):
    class SolverStub:
        @staticmethod
        def available(exception_flag=False):
            return True

        @staticmethod
        def solve(model, **kwargs):
            assert kwargs["load_solutions"] is False
            return SimpleNamespace(
                solver=SimpleNamespace(
                    termination_condition="infeasible",
                    status="ok",
                ),
                solution=[],
                problem=[],
            )

    monkeypatch.setattr(
        hybrid_bess_optimization.pyo,
        "SolverFactory",
        lambda solver_name: SolverStub(),
    )

    with pytest.raises(RuntimeError, match="No feasible solution found"):
        ScenarioDependentBESSModel(audit_config()).solve()


def test_extract_best_bound_for_maximization():
    problem = SimpleNamespace(upper_bound=1709.20203374, lower_bound=1706.87582223)

    assert _extract_best_objective_bound(
        problem, hybrid_bess_optimization.pyo.maximize
    ) == pytest.approx(1709.20203374)


def test_extract_best_bound_for_minimization():
    problem = SimpleNamespace(lower_bound=12.5, upper_bound=15.0)

    assert _extract_best_objective_bound(
        problem, hybrid_bess_optimization.pyo.minimize
    ) == pytest.approx(12.5)


def test_extract_best_bound_returns_none_when_unavailable():
    problem = SimpleNamespace()

    assert _extract_best_objective_bound(
        problem, hybrid_bess_optimization.pyo.maximize
    ) is None
    assert _extract_best_objective_bound(
        None, hybrid_bess_optimization.pyo.maximize
    ) is None
