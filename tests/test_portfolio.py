"""Pruebas de la sección 6.12 (Expected Loss, cartera y stress testing)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, data, decision as dec, evaluation as ev, features, portfolio as pf, scorecard as sc  # noqa: E402

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
FX = features.build_features(POP)
VAL = FX[FX["sample"] == "VAL"]
CARD = sc.Scorecard.load(cfg.ROOT / "models" / "scorecard_pd_v1.json")
PLATT = ev.PlattCalibrator().fit(CARD.predict_pd(VAL), VAL[cfg.TARGET])
TTD = features.build_features(RAW[RAW[cfg.DATE_COL].dt.year == 2025])
PD_TTD = PLATT.transform(CARD.predict_pd(TTD))


def test_expected_loss_es_pd_por_ead_por_lgd():
    el = pf.expected_loss_frame(TTD, PD_TTD, ead_factor=0.415, lgd=0.686)
    assert np.allclose(el["el"], el["pd"] * el["ead"] * el["lgd"])
    assert np.allclose(el["ead"], 0.415 * TTD["requested_amount"])
    r = pf.portfolio_summary(el)
    assert np.isclose(r["el_sobre_monto"], el["el"].sum() / el["monto"].sum())


def test_shock_sobre_odds_mantiene_la_pd_en_rango_y_es_monotono():
    e = pf.Escenario("x2", odds_pd=2.0)
    p = e.pd_shock(PD_TTD)
    assert (p > 0).all() and (p < 1).all()
    assert (p >= PD_TTD - 1e-12).all()
    assert np.isclose(pf.Escenario("neutro").pd_shock(PD_TTD), PD_TTD).all()


def test_capital_irb_crece_con_pd_y_lgd():
    ead = np.full(100, 1000.0)
    bajo = pf.basel_capital(np.full(100, 0.05), 0.6, ead)
    alto = pf.basel_capital(np.full(100, 0.20), 0.6, ead)
    mas_lgd = pf.basel_capital(np.full(100, 0.05), 0.9, ead)
    assert alto["capital_sobre_ead"] > bajo["capital_sobre_ead"] > 0
    assert mas_lgd["capital_sobre_ead"] > bajo["capital_sobre_ead"]
    assert np.isclose(bajo["rwa"], bajo["capital"] * 12.5)


def test_escenarios_empeoran_y_la_politica_reduce_la_aprobacion():
    escenarios = [pf.Escenario("Base", 1.0, 0.686, 0.415), pf.Escenario("Severe", 2.0, 0.745, 0.486)]
    r = pf.run_scenarios(TTD, PD_TTD, escenarios, dec.DecisionPolicy())
    assert r.loc["Severe", "el_sobre_monto"] > r.loc["Base", "el_sobre_monto"]
    assert r.loc["Severe", "aprobacion_final"] < r.loc["Base", "aprobacion_final"]   # estabilizador automático
    assert r.loc["Severe", "capital_sobre_ead"] > r.loc["Base", "capital_sobre_ead"]


def test_el_restateado_usa_la_misma_base_que_el_umbral():
    """El umbral del apetito se restatea con el mismo factor con el que cambia la LGD."""
    factor = 0.686 / cfg.LGD_BASELINE
    verde_restateado = 0.030 * factor
    el_contable = pf.expected_loss_frame(TTD, PD_TTD, lgd=cfg.LGD_BASELINE)["el"].sum()
    el_economico = pf.expected_loss_frame(TTD, PD_TTD, lgd=0.686)["el"].sum()
    assert np.isclose(el_economico / el_contable, factor, atol=1e-6)
    assert verde_restateado > 0.030


def test_hhi_y_tablero_por_segmento():
    assert np.isclose(pf.hhi([1, 1, 1, 1]), 0.25) and np.isclose(pf.hhi([1, 0, 0]), 1.0)
    el = pf.expected_loss_frame(TTD, PD_TTD)
    t = pf.segment_dashboard(TTD, el, {"Región": TTD["region"]}, TTD[cfg.TARGET])
    assert np.isclose(t["pct_monto"].sum(), 1.0) and np.isclose(t["pct_el"].sum(), 1.0)
    assert (t["el_sobre_monto"] > 0).all()


def test_tablero_html_existe_y_es_autocontenido():
    ruta = cfg.REPORTS / "dashboard_cartera.html"
    if not ruta.exists():
        return
    html = ruta.read_text(encoding="utf-8")
    assert "<table" in html and "data:image/png;base64," in html      # tablas y figuras embebidas
    assert "http://" not in html and "https://" not in html           # sin dependencias externas
