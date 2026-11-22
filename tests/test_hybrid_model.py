import numpy as np
import pytest
from hybrid_bess_optimization import HybridBESSModel


def _cfg(T=16, S=3, beta=0.2):
    rng = np.random.default_rng(0)
    lda = np.where(np.arange(T) < T // 2, 30.0, 120.0)
    lim = lda + rng.normal(0, 10, (S, T))
    pv = np.where(np.arange(T) < T // 2, 5.0, 0.0)
    return dict(p_pv=pv, lambda_da=lda, lambda_imb=lim,
                pi_s=[1.0 / S] * S, beta=beta)


def test_model_builds_and_solves():
    res = HybridBESSModel(_cfg()).solve()
    assert np.isfinite(res["expected_pnl"])


def test_soc_within_bounds():
    res = HybridBESSModel(_cfg()).solve()
    soc = np.array(res["soc"])
    assert (soc >= 1.0 - 1e-6).all()
    assert (soc <= 9.0 + 1e-6).all()


def test_no_simultaneous_charge_discharge():
    res = HybridBESSModel(_cfg()).solve()
    prod = np.array(res["p_ch"]) * np.array(res["p_dis"])
    assert (prod < 1e-6).all()


def _phys(cfg, res):
    return cfg["p_pv"] + np.array(res["p_dis"]) - np.array(res["p_ch"])


def test_zero_imbalance_means_nomination_equals_physical_position():
    cfg = _cfg()
    cfg["max_imbalance_mw"] = 0.0
    res = HybridBESSModel(cfg).solve()
    gap = np.abs(np.array(res["p_da"]) - _phys(cfg, res))
    assert (gap < 1e-6).all()


def test_default_imbalance_band_is_respected():
    cfg = _cfg()
    res = HybridBESSModel(cfg).solve()
    gap = np.abs(np.array(res["p_da"]) - _phys(cfg, res))
    assert (gap <= 1.0 + 1e-6).all()


def test_negative_imbalance_limit_is_rejected():
    cfg = _cfg()
    cfg["max_imbalance_mw"] = -0.1

    with pytest.raises(ValueError, match="finite and non-negative"):
        HybridBESSModel(cfg)


def test_non_finite_imbalance_limit_is_rejected():
    cfg = _cfg()
    cfg["max_imbalance_mw"] = np.inf

    with pytest.raises(ValueError, match="finite and non-negative"):
        HybridBESSModel(cfg)
