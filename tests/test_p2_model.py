import numpy as np
import pytest

from hybrid_bess_optimization import (
    ScenarioDependentBESSModel,
    weighted_lower_tail_cvar,
)


def p2_config(n_scenarios=3, n_steps=16):
    rng = np.random.default_rng(7)
    pv = np.where(np.arange(n_steps) < n_steps // 2, 5.0, 0.0)
    pv_s = np.repeat(pv[np.newaxis, :], n_scenarios, axis=0)
    pv_s *= rng.uniform(0.8, 1.2, size=(n_scenarios, 1))
    da = np.where(np.arange(n_steps) < n_steps // 2, 30.0, 120.0)
    return {
        "dt": 0.25,
        "p_pv": pv_s,
        "lambda_da": da,
        "lambda_imb": np.repeat(da[np.newaxis, :], n_scenarios, axis=0),
        "pi_s": [1.0 / n_scenarios] * n_scenarios,
        "alpha_cvar": 0.95,
        "beta": 0.20,
        "c_curtail_eur_mwh": 5.0,
        "max_imbalance_mw": 10.0,
    }


def test_p2_builds_and_returns_complete_output():
    res = ScenarioDependentBESSModel(p2_config()).solve()
    assert np.isfinite(res["expected_pnl"])
    assert np.isfinite(res["cvar"])
    assert np.isfinite(res["objective"])
    assert len(res["scenario_profit"]) == 3
    assert len(res["p_ch"]) == 3
    assert len(res["p_curtail"]) == 3
    assert len(res["p_grid"]) == 3
    assert len(res["p_imb"]) == 3
    assert abs(res["cvar"] - res["independent_weighted_cvar"]) < 1e-4


def test_p2_curtailment_bounds_and_grid_balance():
    cfg = p2_config()
    model = ScenarioDependentBESSModel(cfg)
    res = model.solve()
    pv = model.p_pv
    for s in range(model.S):
        assert all(0 <= res["p_curtail"][s][t] <= pv[s, t] + 1e-6
                   for t in range(model.T))
        for t in range(model.T):
            physical = (
                pv[s, t] - res["p_curtail"][s][t]
                + res["p_dis"][s][t] - res["p_ch"][s][t]
            )
            assert abs(res["p_grid"][s][t] - physical) < 1e-6
            assert abs(res["p_imb"][s][t] -
                       (res["p_grid"][s][t] - res["p_da"][t])) < 1e-6
            assert abs(res["p_imb"][s][t]) <= cfg["max_imbalance_mw"] + 1e-6


def test_p2_soc_and_no_simultaneous_charge_discharge():
    cfg = p2_config(n_scenarios=2)
    model = ScenarioDependentBESSModel(cfg)
    res = model.solve()
    soc = np.asarray(res["soc"])
    assert np.all(soc >= 1.0 - 1e-6)
    assert np.all(soc <= 9.0 + 1e-6)
    for s in range(model.S):
        assert np.all(np.asarray(res["p_ch"][s]) *
                      np.asarray(res["p_dis"][s]) < 1e-6)


def test_weighted_cvar_agrees_for_equal_scenarios():
    profits = np.array([-8.0, 2.0, 4.0, 10.0])
    probabilities = np.array([0.25] * 4)
    assert weighted_lower_tail_cvar(profits, probabilities, 0.75) == pytest.approx(-8.0)
    assert weighted_lower_tail_cvar(profits, probabilities, 0.5) == pytest.approx(-3.0)


def test_weighted_cvar_supports_unequal_probabilities():
    profits = np.array([-10.0, 0.0, 10.0])
    probabilities = np.array([0.2, 0.3, 0.5])
    assert weighted_lower_tail_cvar(profits, probabilities, 0.8) == pytest.approx(-10.0)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"pi_s": [0.2, 0.2]}, "probabilities must sum"),
        ({"pi_s": [-0.1, 1.1]}, "nonnegative"),
        ({"alpha_cvar": 1.0}, "strictly between"),
        ({"beta": 1.1}, "within"),
        ({"c_curtail_eur_mwh": -1.0}, "non-negative"),
    ],
)
def test_p2_rejects_invalid_economic_parameters(kwargs, match):
    cfg = p2_config(n_scenarios=2)
    cfg.update(kwargs)
    with pytest.raises(ValueError, match=match):
        ScenarioDependentBESSModel(cfg)
