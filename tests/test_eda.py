"""Pruebas de la sección 6.4 (EDA orientado a riesgo)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, data, eda, features  # noqa: E402

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
FX = features.build_features(POP)
DEV, VAL = FX[FX["sample"] == "DEV"], FX[FX["sample"] == "VAL"]


def test_wilson_contiene_la_proporcion():
    lo, hi = eda.wilson_ci(np.array([0, 5, 50]), np.array([20, 50, 100]))
    p = np.array([0, 0.1, 0.5])
    assert (lo <= p + 1e-12).all() and (hi >= p - 1e-12).all() and (lo >= 0).all() and (hi <= 1).all()


def test_bh_fdr_monotono_y_acotado():
    p = np.array([0.001, 0.04, 0.03, 0.5, 0.2])
    q = eda.bh_fdr(p)
    assert (q >= p - 1e-12).all() and (q <= 1).all()
    orden = np.argsort(p)
    assert (np.diff(q[orden]) >= -1e-12).all()


def test_tabla_de_default_suma_la_muestra():
    t = eda.bad_rate_table(DEV, "bureau_score", eda.quantile_edges(DEV["bureau_score"], 10))
    assert t["creditos"].sum() == len(DEV) and t["defaults"].sum() == DEV[cfg.TARGET].sum()
    assert "Faltante" in t.index


def test_tamizaje_marca_al_buro_y_no_a_la_distancia():
    cands = data.pd_candidate_features() + ["dti_post", "ahorro_sobre_monto"]
    cats = ["region", "channel", "employment_type"]
    t = eda.univariate_screening(DEV, VAL, [c for c in cands if c not in cats], cats).set_index("variable")
    assert t.loc["bureau_score", "senal_en_dev"] and not t.loc["distance_to_branch_km", "senal_en_dev"]


def test_desplazamiento_de_nivel_detecta_un_intercepto_sintetico():
    rng = np.random.default_rng(0)
    n = 20000
    s = rng.normal(size=n)
    base = pd.DataFrame({"s": s, cfg.TARGET: rng.random(n) < 1 / (1 + np.exp(-(-2 - 0.8 * s)))}).astype({cfg.TARGET: int})
    s2 = rng.normal(size=n)
    shift = pd.DataFrame({"s": s2, cfg.TARGET: rng.random(n) < 1 / (1 + np.exp(-(-1.5 - 0.8 * s2)))}).astype({cfg.TARGET: int})
    r = eda.level_shift_test(base, shift, "s")
    assert r["p_nivel"] < 1e-6 and r["p_pendiente"] > 0.01 and abs(r["cambio_log_odds"] - 0.5) < 0.1


def test_eda_no_usa_oot_en_las_relaciones_variable_riesgo():
    """Las funciones reciben muestras explícitas; el notebook solo les pasa DEV y VAL."""
    assert set(DEV["sample"]) == {"DEV"} and set(VAL["sample"]) == {"VAL"}


def test_concentracion_de_perdida_suma_uno_y_usa_cortes_fijos():
    edges = eda.quantile_edges(DEV["bureau_score"], 5)
    etq = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    for d in (DEV, VAL):
        c = eda.loss_concentration(d, "bureau_score", edges, etq)
        assert np.isclose(c["pct_perdida"].sum(), 1) and np.isclose(c["pct_creditos"].sum(), 1)
        assert c["creditos"].sum() == len(d)
    c_dev = eda.loss_concentration(DEV, "bureau_score", edges, etq)
    assert c_dev.loc["Q1", "pct_perdida"] > 2 * c_dev.loc["Q1", "pct_creditos"] * 0.9   # el quintil bajo concentra pérdida
