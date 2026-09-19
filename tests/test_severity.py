"""Pruebas de las secciones 6.10 y 6.11 (EAD y LGD).

Ejecutar desde la raíz del repo:  python -m pytest tests
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, data, features, severity as sv  # noqa: E402

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
FX = features.build_features(POP)
SEV = sv.build_severity_frame(FX)
DEV, VAL, OOT = (SEV[SEV["sample"] == s] for s in cfg.SAMPLE_ORDER)
VARS = ["bureau_score", "dti_post", "term_months", "requested_amount", "monthly_income", "ahorro_sobre_monto"]


def test_poblacion_de_severidad_son_los_defaults_con_exposicion():
    assert len(SEV) == int(FX[cfg.TARGET].sum()) == 671
    assert SEV["ead_at_default"].notna().all() and SEV["lgd"].notna().all()
    assert SEV["ccf_observed"].isna().all()              # producto sin línea: no hay CCF que modelar
    assert (SEV["ead_ratio"].between(0, 1)).all()


def test_identidad_de_la_lgd():
    calc = (SEV["ead_at_default"] - SEV["recovery_amount_total"] + SEV["recovery_cost_total"]) / SEV["ead_at_default"]
    assert (calc - SEV["lgd"]).abs().max() < 1e-4


def test_mes_implicito_detecta_la_incoherencia_con_la_amortizacion():
    """La mitad de los defaults exige más de 12 cuotas pagadas: es el hallazgo de 6.10 §3."""
    k = sv.implied_month_on_book(SEV)
    assert (k > 0).all() and (k <= SEV["term_months"] + 1e-6).all()
    assert 0.35 < float((k > 12).mean()) < 0.65
    k_ref = sv.implied_month_on_book(SEV, cfg.REFERENCE_ANNUAL_RATE)
    assert abs(float((k > 12).mean()) - float((k_ref > 12).mean())) < 0.05   # no depende de la tasa usada


def test_baseline_segmentado_usa_el_global_en_segmentos_chicos():
    b = sv.SegmentedBaseline(["bureau_score"], {"bureau_score": [0, 600, 660, 700, 900]}, min_n=1000).fit(DEV, "lgd")
    assert np.allclose(b.predict(VAL), b.global_)         # ningún segmento llega al mínimo: todo al promedio global
    b2 = sv.SegmentedBaseline().fit(DEV, "lgd")
    assert np.isclose(b2.predict(VAL)[0], DEV["lgd"].mean())


def test_modelos_acotados_predicen_dentro_del_rango():
    for modelo in (sv.FractionalLogit(VARS), sv.BoundedGBM(VARS)):
        p = modelo.fit(DEV, "lgd").predict(VAL)
        assert (p >= 0).all() and (p <= 1).all()


def test_ningun_modelo_le_gana_al_baseline_en_val():
    """Resultado de 6.10 y 6.11: fuera de muestra el baseline no se supera de forma material."""
    for y in ("ead_ratio", "lgd"):
        base = sv.evaluate(VAL[y], sv.SegmentedBaseline().fit(DEV, y).predict(VAL))
        gbm = sv.evaluate(VAL[y], sv.BoundedGBM(VARS).fit(DEV, y).predict(VAL))
        frac = sv.evaluate(VAL[y], sv.FractionalLogit(VARS).fit(DEV, y).predict(VAL))
        assert gbm["mae"] > base["mae"]                   # el boosting sobreajusta
        assert frac["mae"] > base["mae"] - 0.005          # la logística fraccional no mejora de forma material
        assert abs(base["sesgo"]) < 0.02                  # y el baseline no viene sesgado


def test_lgd_economica_sube_con_la_tasa_de_descuento():
    contable = float(SEV["lgd"].mean())
    anterior = contable
    for tasa in (0.0, 0.10, 0.20, 0.30):
        actual = float(sv.lgd_economica(SEV, tasa).mean())
        assert actual >= anterior - 1e-9
        anterior = actual
    assert np.isclose(float(sv.lgd_economica(SEV, 0.0).mean()), contable, atol=1e-6)
    assert float(sv.lgd_economica(SEV, 0.10).mean()) > contable + 0.02     # el descuento sí mueve la aguja


def test_downturn_usa_la_peor_cosecha_y_no_mira_oot():
    dev_val = SEV[SEV["sample"].isin(["DEV", "VAL"])]
    d = sv.downturn_lgd(dev_val)
    assert d["anio_peor_cosecha"] <= 2024                                   # la cosecha OOT no entra
    assert d["peor_cosecha"] >= d["promedio_largo_plazo"]
    assert 0 <= d["recargo_downturn"] < 0.05                                # severidad poco cíclica


def test_parametros_de_config_coinciden_con_el_artefacto():
    import json
    art = json.loads((cfg.ROOT / "models" / "ead_lgd_v1.json").read_text(encoding="utf-8"))
    assert np.isclose(cfg.EAD_FACTOR_BASELINE, art["ead"]["factor"], atol=0.001)
    assert np.isclose(cfg.LGD_BASELINE, art["lgd"]["lgd_contable"], atol=0.001)
    assert np.isclose(cfg.LGD_DOWNTURN, art["lgd"]["lgd_downturn_dev_val"], atol=0.001)
    assert np.isclose(cfg.EAD_FACTOR_BASELINE, DEV["ead_ratio"].mean(), atol=0.001)
    assert np.isclose(cfg.LGD_BASELINE, DEV["lgd"].mean(), atol=0.001)
