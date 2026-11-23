import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
DA_FILE = DATA / "raw" / "day_ahead_prices.csv"
PV_FILE = DATA / "pv_profile_10mw_2026-08-06_15min.csv"

DA_MD5 = "af28dd88716d7972e88c7f3fb8b31051"


def _load_da():
    df = pd.read_csv(DA_FILE, sep=";", encoding="utf-8-sig")
    col = [c for c in df.columns if c.startswith("Germany/Luxembourg")][0]
    return pd.DataFrame({
        "start": pd.to_datetime(df["Start date"], format="%b %d, %Y %I:%M %p"),
        "price": pd.to_numeric(df[col], errors="coerce"),
    })


def test_day_ahead_file_is_unmodified_smard_download():
    assert hashlib.md5(DA_FILE.read_bytes()).hexdigest() == DA_MD5


def test_day_ahead_prices_basic_properties():
    d = _load_da()
    assert len(d) == 1056
    assert d["price"].notna().all()
    assert d["start"].is_monotonic_increasing
    assert (d["start"].diff().dropna() == pd.Timedelta(minutes=15)).all()
    assert round(d["price"].mean(), 2) == 140.20
    assert round(d["price"].min(), 2) == -6.21
    assert round(d["price"].max(), 2) == 249.92
    assert int((d["price"] < 0).sum()) == 40


def test_pv_profile_basic_properties():
    d = pd.read_csv(PV_FILE, parse_dates=["timestamp"])
    assert len(d) == 96
    assert (d["timestamp"].diff().dropna() == pd.Timedelta(minutes=15)).all()
    assert (d["p_pv_mw"] >= 0).all()
    assert abs(d["p_pv_mw"].max() - 10.0) < 1e-9
    scale = 10.0 / d["pv_national_mw"].max()
    assert np.allclose(d["p_pv_mw"], d["pv_national_mw"] * scale)
