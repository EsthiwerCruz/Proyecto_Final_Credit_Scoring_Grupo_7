"""Pruebas de las secciones 6.6 a 6.9 (modelos PD, validación, fairness y motor de decisión).

Ejecutar desde la raíz del repo:  python -m pytest tests
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import (config as cfg, data, decision as dec, evaluation as ev, fairness as fr,  # noqa: E402
                 features, models, pipeline, scorecard as sc)

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
FX = features.build_features(POP)
DEV, VAL, OOT = (FX[FX["sample"] == s].copy() for s in cfg.SAMPLE_ORDER)
COLS_IN = pipeline.pipeline_input_columns()
PIPE = pipeline.build_pipeline().fit(DEV[COLS_IN])
CARD = sc.Scorecard.load(cfg.ROOT / "models" / "scorecard_pd_v1.json")
PD_DEV, PD_VAL = CARD.predict_pd(DEV), CARD.predict_pd(VAL)


# --------------------------------------------------------------------------- 6.6
def test_folds_temporales_no_miran_el_futuro():
    anio = DEV[cfg.DATE_COL].dt.year.to_numpy()
    for tr, te in models.temporal_folds(DEV):
        assert anio[tr].max() < anio[te].min()          # entrenar siempre antes de validar
        assert tr.sum() > 0 and te.sum() > 0


def test_veto_de_fairness_saca_las_columnas_sensibles():
    columnas = list(PIPE.transform(DEV[COLS_IN]).columns)
    vetadas = models.columnas_vetadas(columnas)
    assert {"age", "cash_income_share", "distance_to_branch_km", "household_dependents"} <= set(vetadas)
    assert all(c.startswith("region_") for c in vetadas if c.startswith("region"))
    assert "bureau_score" not in vetadas and "dti_post" not in vetadas


def test_restricciones_monotonas_siguen_la_direccion_de_negocio():
    mono = models.monotone_vector(["bureau_score", "dti_post", "requested_amount"])
    assert mono == [-1, 1, 0]                            # buró baja el riesgo, DTI lo sube, monto sin dirección


def test_champion_challenger_marca_la_perdida_significativa():
    comparacion = pd.DataFrame({"gini_val": [0.35, 0.20]}, index=["bueno", "malo"])
    class _C:
        def __init__(self, p): self.p = p
        def pd_hat(self, df): return self.p
    rng = np.random.default_rng(cfg.SEED)
    y = VAL[cfg.TARGET].to_numpy()
    bueno = PD_VAL
    malo = np.clip(PD_VAL + rng.normal(0, 0.25, len(y)), 1e-4, 1 - 1e-4)
    t = models.champion_challenger(comparacion, {"bueno": _C(bueno), "malo": _C(malo)}, VAL, ["bueno", "malo"], n_boot=300)
    assert not t.loc["bueno", "peor_de_forma_significativa"]
    assert t.loc["malo", "peor_de_forma_significativa"]


# --------------------------------------------------------------------------- 6.7
def test_metricas_de_discriminacion_y_clasificacion():
    r = ev.full_report(VAL[cfg.TARGET], PD_VAL, threshold=0.18)
    assert 0.3 < r["gini"] < 0.5 and 0 < r["ks"] < 1
    assert r["vp"] + r["fp"] + r["fn"] + r["vn"] == len(VAL)
    assert np.isclose(r["precision"], r["vp"] / (r["vp"] + r["fp"]))
    assert np.isclose(r["recall"], r["vp"] / (r["vp"] + r["fn"]))


def test_deciles_ordenan_el_riesgo_y_suman_la_muestra():
    t = ev.decile_table(OOT[cfg.TARGET], CARD.predict_pd(OOT))
    assert t["creditos"].sum() == len(OOT) and t["defaults"].sum() == OOT[cfg.TARGET].sum()
    assert t.loc[1, "default_rate"] > t.loc[10, "default_rate"]      # D1 más riesgoso que D10
    assert np.isclose(t["captura_malos_acum"].iloc[-1], 1.0)


def test_platt_corrige_el_nivel_y_no_cambia_el_orden():
    platt = ev.PlattCalibrator().fit(PD_VAL, VAL[cfg.TARGET])
    p_val = platt.transform(PD_VAL)
    antes = ev.calibration_metrics(VAL[cfg.TARGET], PD_VAL)
    despues = ev.calibration_metrics(VAL[cfg.TARGET], p_val)
    assert abs(despues["observado_sobre_predicho"] - 1) < abs(antes["observado_sobre_predicho"] - 1)
    assert np.isclose(ev.discrimination(VAL[cfg.TARGET], p_val)["auc"],
                      ev.discrimination(VAL[cfg.TARGET], PD_VAL)["auc"])      # transformación monótona
    p_oot = platt.transform(CARD.predict_pd(OOT))
    assert abs(p_oot.mean() - OOT[cfg.TARGET].mean()) < abs(CARD.predict_pd(OOT).mean() - OOT[cfg.TARGET].mean())


# --------------------------------------------------------------------------- 6.8
def test_air_acotado_y_alerta_de_cuatro_quintos():
    decision = pd.Series(["APPROVE"] * 80 + ["REJECT"] * 20 + ["APPROVE"] * 50 + ["REJECT"] * 50)
    grupo = pd.Series(["A"] * 100 + ["B"] * 100)
    t = fr.adverse_impact_ratio(decision, grupo)
    assert np.isclose(t.loc["A", "air"], 1.0) and np.isclose(t.loc["B", "air"], 0.5 / 0.8)
    assert t.loc["B", "alerta_4_5"] and not t.loc["A", "alerta_4_5"]


def test_el_score_no_reconstruye_los_atributos_sensibles():
    W = sc.woe_frame(DEV, CARD.binnings, CARD.variables)
    assert fr.proxy_strength(W, DEV["cash_income_share"])["r2_cv"] < 0.05
    assert fr.proxy_strength(W, DEV["region"])["auc_max_cv"] < 0.60


def test_explicacion_local_del_scorecard_es_exacta():
    fila = VAL.iloc[[0]]
    t = fr.scorecard_local_explanation(CARD, fila)
    assert np.isclose(t["puntos"].sum(), CARD.score(fila)[0])
    assert (t["puntos_perdidos"] >= 0).all()


# --------------------------------------------------------------------------- 6.9
def _ttd_2024():
    return features.build_features(RAW[RAW[cfg.DATE_COL].dt.year == 2024])


def test_contraoferta_respeta_la_capacidad_de_pago():
    t = _ttd_2024()
    pol = dec.DecisionPolicy()
    monto = pol.recommended_amount(t)
    r = (1 + pol.reference_rate) ** (1 / 12) - 1
    cuota = monto * r / (1 - (1 + r) ** -t["term_months"].to_numpy(dtype=float))
    dti_post = (t["monthly_debt_payment"].to_numpy() + cuota) / t["monthly_income"].to_numpy()
    con_ingreso = t["monthly_income"].notna().to_numpy() & (monto > 0)
    assert (dti_post[con_ingreso] <= pol.dti_auto_max + 1e-6).all()
    assert (monto <= t["requested_amount"].to_numpy() + 1e-9).all()


def test_motor_devuelve_tres_salidas_con_motivo_monto_y_tasa():
    t = _ttd_2024()
    pol = dec.DecisionPolicy()
    p = np.clip(CARD.predict_pd(t) * 1.4, 1e-4, 0.99)
    d = pol.decide(t, p)
    assert set(d["decision"]) <= {dec.APPROVE, dec.REVIEW, dec.REJECT}
    assert set(d["decision"]) == {dec.APPROVE, dec.REVIEW, dec.REJECT}
    assert d["motivo"].notna().all()
    assert d.loc[d.decision == dec.REJECT, "monto_recomendado"].isna().all()
    aprobados = d.decision == dec.APPROVE
    assert (d.loc[aprobados, "tasa_recomendada"].between(cfg.RATE_FLOOR, cfg.RATE_CAP)).all()
    assert (d.loc[aprobados, "pd_calibrada"] <= pol.pd_approve_max + 1e-9).all()


def test_sin_informacion_nunca_se_rechaza_en_automatico():
    """Sin score de buró o sin ingreso, la PD se calcula con un insumo imputado: va a analista, no a rechazo."""
    t = _ttd_2024()
    pol = dec.DecisionPolicy()
    p = np.clip(CARD.predict_pd(t) * 1.6, 1e-4, 0.99)          # se fuerza una PD alta para el caso extremo
    d = pol.decide(t, p)
    sin_info = t["bureau_score"].isna() | t["monthly_income"].isna()
    assert (d.loc[sin_info, "decision"] != dec.REJECT).all()
    assert (d.loc[sin_info, "decision"] == dec.REVIEW).all()


def test_revision_por_capacidad_recibe_un_monto_viable_al_tope_duro():
    """A quien va a analista por capacidad se le calcula el techo del 60%, no un monto cero."""
    t = _ttd_2024()
    pol = dec.DecisionPolicy()
    d = pol.decide(t, CARD.predict_pd(t))
    por_capacidad = d["motivo"].str.startswith("Capacidad de pago insuficiente:")
    montos = d.loc[por_capacidad, "monto_recomendado"]
    assert (montos > 0).any()
    topes = pol.max_amount_by_capacity(t.loc[por_capacidad.to_numpy()], pol.dti_hard_max)
    assert (montos.to_numpy() <= topes + 100).all()             # nunca por encima del tope duro (redondeo a S/ 100)


def test_pricing_cubre_costos_y_perdida_esperada():
    t = _ttd_2024().head(200)
    pol = dec.DecisionPolicy()
    p = np.clip(CARD.predict_pd(t), 1e-4, 0.99)
    tasa = pol.risk_based_rate(p, t)
    plazo = t["term_months"].to_numpy(dtype=float) / 12
    prima = p * cfg.EAD_FACTOR_BASELINE * cfg.LGD_BASELINE / (cfg.AVG_BALANCE_FACTOR * plazo)
    minimo = cfg.COST_OF_FUNDS + cfg.OPERATING_COST_RATE + prima + cfg.TARGET_MARGIN
    assert (tasa >= np.minimum(minimo, cfg.RATE_CAP) - 1e-9).all()


def test_curva_de_tradeoff_es_monotona_en_aprobacion():
    t = _ttd_2024()
    pol = dec.DecisionPolicy()
    p = np.clip(CARD.predict_pd(t) * 1.4, 1e-4, 0.99)
    curva = dec.tradeoff_curve(t, p, pol, grid=[0.10, 0.15, 0.20, 0.25])
    assert (np.diff(curva["aprobacion"].to_numpy()) >= -1e-9).all()      # aprobar más al subir el umbral
    assert (curva["default_esperado"].diff().dropna() >= -0.02).all()    # y no bajar el riesgo al hacerlo


def test_swap_out_tiene_peor_default_que_los_que_se_mantienen():
    t = _ttd_2024()
    pol = dec.DecisionPolicy()
    platt = ev.PlattCalibrator().fit(PD_VAL, VAL[cfg.TARGET])
    d = pol.decide(t, platt.transform(CARD.predict_pd(t)))
    swap = dec.swap_analysis(t, d, t[cfg.APPROVED_FLAG])
    assert swap.loc["Swap-out: salen", "default_observado"] > swap.loc["Se mantienen aprobados", "default_observado"]


def test_artefactos_de_politica_y_calibracion_existen_y_son_coherentes():
    import json
    calib = json.loads((cfg.ROOT / "models" / "calibrador_platt_v1.json").read_text(encoding="utf-8"))
    politica = json.loads((cfg.ROOT / "models" / "politica_decision_v1.json").read_text(encoding="utf-8"))
    assert calib["calibrador"]["metodo"] == "platt"
    assert politica["umbrales"]["pd_approve_max"] == cfg.PD_APPROVE_MAX
    assert politica["umbrales"]["pd_reject_min"] == cfg.PD_REJECT_MIN
    assert politica["resultados_2024"]["default_cartera_final"] <= 0.11      # límite de riesgo del apetito
    assert politica["resultados_2024"]["el_cartera_final"] <= 0.03
