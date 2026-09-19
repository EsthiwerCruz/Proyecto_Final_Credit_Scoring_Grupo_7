"""Pruebas de la sección 6.5 (scorecard tradicional).

Ejecutar desde la raíz del repo:  python -m pytest tests
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, data, features, scorecard as sc  # noqa: E402

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
FX = features.build_features(POP)
DEV, VAL, OOT = (FX[FX["sample"] == s] for s in cfg.SAMPLE_ORDER)
FINALES = ["bureau_score", "dti_post", "ahorro_sobre_monto"]
BINS = {v: sc.fit_binning(DEV, v) for v in FINALES}
CARD, COEFS = sc.fit_scorecard(DEV, FINALES, BINS)
ARTEFACTO = cfg.ROOT / "models" / "scorecard_pd_v1.json"


def test_binning_respeta_minimos_y_monotonia():
    for v, b in BINS.items():
        t = b.table(DEV[v], DEV[cfg.TARGET])
        t = t[t["orden"] >= 0]
        assert (t["pct_creditos"] >= sc.BIN_MIN_SHARE - 1e-9).all(), v
        assert (t["defaults"] >= sc.BIN_MIN_BADS).all(), v
        assert len(t) <= sc.BIN_MAX
        woe = np.asarray(b.woe)
        # WOE alto = menos riesgo: con tendencia "-" (buró, ahorro) el WOE sube con el valor; con "+" (dti_post) baja.
        paso = np.diff(woe)
        assert (paso > 0).all() if sc.EXPECTED_TREND[v] == "-" else (paso < 0).all(), v


def test_faltante_y_categoria_no_vista_tienen_woe_neutral():
    assert BINS["bureau_score"].transform(pd.Series([np.nan]))[0] == 0.0
    b = sc.fit_binning(DEV, "channel")
    assert b.transform(pd.Series(["canal_inexistente"]))[0] == 0.0


def test_coeficientes_negativos_y_significativos():
    c = COEFS.drop(index="intercepto")
    assert (c["coef"] < 0).all() and (c["p_value"] < sc.COEF_ALPHA).all()
    assert sc.vif(sc.woe_frame(DEV, BINS, FINALES)).max() < sc.VIF_MAX


def test_escala_base_odds_y_pdo():
    """El puntaje base corresponde a las odds base y cada PDO puntos las odds se duplican."""
    odds_buenos = lambda s: (1 - CARD.score_to_pd(s)) / CARD.score_to_pd(s)
    assert np.isclose(odds_buenos(CARD.base_score), CARD.base_odds)
    assert np.isclose(odds_buenos(CARD.base_score + CARD.pdo) / odds_buenos(CARD.base_score), 2.0)


def test_puntos_suman_el_score_y_la_pd_es_coherente():
    exacto = CARD.score(DEV, exact=True)
    assert np.allclose(CARD.score_to_pd(exacto), CARD.predict_pd(DEV))
    redondeado = CARD.score(DEV)
    assert np.allclose(redondeado, CARD.points_frame(DEV).sum(axis=1))
    assert np.abs(redondeado - exacto).max() <= len(FINALES) * 0.5 + 1e-9   # redondeo por característica


def test_bandas_de_score_monotonas_en_dev():
    t = sc.score_band_table(CARD.score(DEV), DEV[cfg.TARGET], [-np.inf, 560, 580, 600, 620, 640, np.inf])
    assert (np.diff(t["default_rate"].to_numpy()) < 0).all()
    assert t["creditos"].sum() == len(DEV)


def test_guardar_y_cargar_reproduce_el_score(tmp_path):
    ruta = tmp_path / "card.json"
    CARD.save(ruta)
    otra = sc.Scorecard.load(ruta)
    assert np.array_equal(otra.score(VAL), CARD.score(VAL))
    assert np.allclose(otra.predict_pd(VAL), CARD.predict_pd(VAL))


def test_artefacto_versionado_coincide_con_el_codigo():
    """El JSON de models/ debe reproducir exactamente el scorecard que ajusta el código."""
    if not ARTEFACTO.exists():
        return
    guardado = sc.Scorecard.load(ARTEFACTO)
    assert guardado.variables == FINALES
    assert np.array_equal(guardado.score(DEV), CARD.score(DEV))


def test_razones_distinguen_dato_faltante():
    fila = DEV.iloc[[0]].copy()
    fila["bureau_score"] = np.nan
    fila["dti_post"] = 0.95
    razones = CARD.reason_codes(fila, n=3)[0]
    assert any("no disponible" in r for r in razones)
    assert "Score de buró bajo" not in razones


def test_seleccion_aplica_fairness_y_detecta_la_inversion_en_val():
    cands = data.pd_candidate_features() + features.DERIVED_CANDIDATES
    tab, _ = sc.univariate_selection(DEV, VAL, OOT, cands, n_perm=20)
    t = tab.set_index("variable")
    assert t.loc["bureau_score", "pasa"] and t.loc["dti_post", "pasa"]
    assert not t.loc["prior_delinquencies_24m", "S6"]            # ordena en DEV pero se invierte en VAL
    for v in sc.EXCLUDED_BY_DESIGN:
        assert not t.loc[v, "S7"] and not t.loc[v, "pasa"]
    assert t["psi_oot"].notna().all()                           # del OOT solo se usa el PSI, sin target


def test_stepwise_elige_el_scorecard_final():
    cands = ["bureau_score", "dti_post", "ahorro_sobre_monto", "monthly_debt_payment"]
    bins = {v: sc.fit_binning(DEV, v) for v in cands}
    pasos = sc.forward_stepwise(DEV, bins, cands)
    assert pasos["entra"].tolist() == FINALES
