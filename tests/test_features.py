"""Pruebas de la sección 6.3 (calidad, faltantes, variables derivadas, pre-selección y pipeline).

Ejecutar desde la raíz del repo:  python -m pytest tests  (o  python tests/test_features.py)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, data, data_dictionary, features, pipeline, quality, validation  # noqa: E402

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
DEV = POP[POP["sample"] == "DEV"]
COLS_IN = pipeline.pipeline_input_columns()
CAT_COLS = ["region", "channel", "employment_type"]


def _toy() -> pd.DataFrame:
    """Solicitud de control con valores redondos para verificar fórmulas."""
    return pd.DataFrame([{
        cfg.DATE_COL: pd.Timestamp("2023-10-15"), "requested_amount": 10_000.0, "term_months": 12.0,
        "monthly_debt_payment": 500.0, "monthly_income": 4_000.0, "cash_income_share": 0.75,
        "household_dependents": 3, "savings_balance": 2_000.0, "active_loans": 3,
        "bureau_inquiries_6m": 4, "employment_tenure_months": 60, "age": 34, "bureau_score": 650.0,
        "dti": 0.125,
    }])


def test_build_features_crea_todas_y_no_muta_la_entrada():
    antes = POP.copy()
    x = features.build_features(POP)
    assert all(c in x.columns for c in features.DERIVED_FEATURES)
    assert len(x) == len(POP)
    pd.testing.assert_frame_equal(POP, antes)  # la función no modifica su entrada


def test_cuota_amortiza_el_credito():
    """La cuota estimada debe dejar saldo cero al final del plazo (amortización francesa)."""
    t = _toy()
    cuota = float(features.build_features(t)["cuota_estimada"].iloc[0])
    r = (1 + cfg.REFERENCE_ANNUAL_RATE) ** (1 / 12) - 1
    saldo = float(t["requested_amount"].iloc[0])
    for _ in range(int(t["term_months"].iloc[0])):
        saldo = saldo * (1 + r) - cuota
    assert abs(saldo) < 1e-6 * float(t["requested_amount"].iloc[0])
    assert cuota * t["term_months"].iloc[0] > t["requested_amount"].iloc[0]  # paga intereses


def test_formulas_de_las_derivadas():
    x = features.build_features(_toy()).iloc[0]
    cuota = x["cuota_estimada"]
    assert np.isclose(x["dti"], 500.0 / 4_000.0)
    assert np.isclose(x["dti_post"], (500.0 + cuota) / 4_000.0)
    assert np.isclose(x["ahorro_sobre_monto"], 2_000.0 / 10_000.0)
    assert x["flag_sin_buro"] == 0 and x["flag_sin_ingreso"] == 0 and x["flag_sin_ahorro"] == 0


def test_formulas_del_pool_evaluado():
    """Las derivadas descartadas se siguen calculando para reproducir la evidencia de 6.3."""
    x = features.build_candidate_pool(_toy()).iloc[0]
    cuota = x["cuota_estimada"]
    assert np.isclose(x["dti_post_verificable"], (500.0 + cuota) / 1_000.0)
    assert np.isclose(x["excedente_per_capita"], (4_000.0 - 500.0 - cuota) / 4)
    assert np.isclose(x["colchon_ahorro_meses"], 2_000.0 / cuota)
    assert np.isclose(x["deuda_por_obligacion"], 500.0 / 4)
    assert np.isclose(x["intensidad_busqueda"], 4 / 4)
    assert np.isclose(x["antiguedad_relativa"], 60 / ((34 - 14) * 12))
    assert x["campana_siembra"] == 1  # octubre
    assert set(features.SCREENING_SPEC) <= set(features.build_candidate_pool(_toy()).columns)


def test_sin_ingreso_no_hay_dti():
    """Regla de consistencia: el dti se recalcula y queda faltante si no hay ingreso."""
    t = _toy()
    t.loc[0, ["bureau_score", "monthly_income", "savings_balance"]] = np.nan
    x = features.build_features(t).iloc[0]
    assert x["flag_sin_buro"] == 1 and x["flag_sin_ingreso"] == 1 and x["flag_sin_ahorro"] == 1
    assert pd.isna(x["dti"]) and pd.isna(x["dti_post"])   # aunque la entrada traía dti = 0.125
    # En la población, las filas sin ingreso quedan sin dti después del recálculo.
    fx = features.build_features(POP)
    assert fx.loc[POP["monthly_income"].isna(), "dti"].isna().all()
    con_ingreso = POP["monthly_income"].notna()
    assert (fx.loc[con_ingreso, "dti"] - POP.loc[con_ingreso, "dti"]).abs().max() < 1e-3


def test_derivadas_no_usan_variables_prohibidas():
    """build_features y el pool deben funcionar sin ninguna columna prohibida presente."""
    sin_prohibidas = POP.drop(columns=data.forbidden_pd_features())
    x = features.build_candidate_pool(sin_prohibidas)
    assert all(c in x.columns for c in features.DERIVED_FEATURES + list(features.SCREENING_SPEC))


def test_auc_con_direccion_y_auc_doblado():
    """El AUC 'doblado' pierde el signo; auc_test lo conserva y da un p-valor."""
    y = DEV[cfg.TARGET]
    auc, p = validation.auc_test(y, DEV["bureau_score"])
    assert auc < 0.5 and p < 1e-6                                # a más score, menos default
    assert validation.univariate_auc(y, DEV["bureau_score"]) > 0.5  # el doblado lo esconde
    rng = np.random.default_rng(cfg.SEED)
    _, p_ruido = validation.auc_test(y, pd.Series(rng.random(len(y)), index=y.index))
    assert p_ruido > 0.01


def test_dti_y_dti_post_intercambiables_por_tramos():
    """Por tramos (como un scorecard) ninguna de las dos aporta sobre la otra en DEV."""
    pool = features.build_candidate_pool(POP)
    dev = pool[pool["sample"] == "DEV"]
    assert validation.lr_test_binned(dev, cfg.TARGET, ["bureau_score", "dti"], ["dti_post"]) > 0.05
    assert validation.lr_test_binned(dev, cfg.TARGET, ["bureau_score", "dti_post"], ["dti"]) > 0.05


def test_preseleccion_solo_con_dev():
    pool = features.build_candidate_pool(POP)
    try:
        features.screen_derived_features(pool)   # trae VAL y OOT: debe rechazarse
        assert False, "La pre-selección aceptó muestras distintas de DEV"
    except ValueError:
        pass


def test_resultado_de_la_preseleccion():
    pool = features.build_candidate_pool(POP)
    scr = features.screen_derived_features(pool[pool["sample"] == "DEV"]).set_index("feature")
    conservadas = set(scr.index[scr.decision == "Conservada"])
    assert conservadas == set(features.DERIVED_CANDIDATES) == {"dti_post", "ahorro_sobre_monto"}
    assert not scr.loc["campana_siembra", "R1"]                 # sin señal y con signo contrario en DEV
    assert not scr.loc["dti_post_verificable", "R4"]            # el efectivo no pasa necesidad de negocio
    assert scr.loc["colchon_ahorro_meses", "redundante_con"] == "ahorro_sobre_monto"


def test_pipeline_se_ajusta_en_dev_y_aplica_igual():
    pipe = pipeline.build_pipeline()
    pipe.fit(DEV[COLS_IN])
    matrices = {s: pipe.transform(POP.loc[POP["sample"] == s, COLS_IN]) for s in cfg.SAMPLE_ORDER}
    columnas = [list(m.columns) for m in matrices.values()]
    assert columnas[0] == columnas[1] == columnas[2]
    for m in matrices.values():
        assert m.isna().sum().sum() == 0
    prohibidas = set(data.forbidden_pd_features())
    cols = set(matrices["DEV"].columns)
    assert not prohibidas & cols
    assert not set(features.POLICY_FLAGS) & cols                                    # indicadores fuera del modelo
    assert not (set(features.SCREENING_SPEC) - set(features.DERIVED_CANDIDATES)) & cols  # descartadas fuera
    assert "dti" not in COLS_IN and cfg.DATE_COL not in COLS_IN                     # dti se recalcula; sin fecha
    # Una solicitud individual, como la puntuará el servicio de scoring.
    assert pipe.transform(RAW.iloc[[0]][COLS_IN]).shape == (1, matrices["DEV"].shape[1])


def test_winsorizer_usa_topes_del_ajuste():
    w = pipeline.Winsorizer(0.01, 0.99)
    train = pd.DataFrame({"x": list(range(100))})
    w.fit(train)
    fuera = pd.DataFrame({"x": [-500, 500]})
    z = w.transform(fuera)
    assert z["x"].iloc[0] == w.lower_["x"] and z["x"].iloc[1] == w.upper_["x"]
    assert z["x"].max() <= train["x"].max()


def test_quality_reportes():
    assert quality.duplicates_report(RAW, [cfg.DATE_COL, "age", "requested_amount"])["registros"].sum() == 0
    reglas = quality.consistency_rules(POP).set_index("regla")
    assert len(reglas) == len(quality.CONSISTENCY_RULES)
    assert reglas.loc[reglas.severidad == "Bloqueante", "violaciones"].sum() == 0   # nada que impida usar la población
    assert reglas.loc["dti informado con ingreso faltante", "violaciones"] == POP["monthly_income"].isna().sum()
    comp = quality.completeness(POP, data.pd_candidate_features())
    assert np.isclose(comp.loc["bureau_score", "total"], POP["bureau_score"].isna().mean())
    estab = quality.temporal_stability(POP, data.pd_candidate_features(), CAT_COLS)
    assert (estab["psi_oot"] < 0.10).all()               # ninguna variable con drift material


def test_faltantes_compatibles_con_mcar():
    rep = quality.missingness_report(RAW, POP, data.pd_candidate_features(), CAT_COLS).set_index("variable")
    assert (rep["auc_cv_modelo_faltante"] < 0.55).all()
    assert (rep["p_modelo_faltante"] > 0.05).all()
    assert rep["conclusion"].str.startswith("Compatible con MCAR").all()
    hist = quality.bureau_history_check(RAW).set_index("variable_de_buro")
    assert (hist["p_ks"].dropna() > 0.05).all()          # sin score no es sinónimo de sin historial


def test_sin_estacionalidad():
    tabla, res = quality.seasonality_test(POP, n_sim=500)
    assert len(tabla) == 12 and tabla["creditos"].sum() == len(POP)
    assert res["p_chi2"] > 0.05 and res["p_set_dic"] > 0.05


def test_diccionario_tecnico_cubre_todo():
    dic = data_dictionary.technical_dictionary()
    assert set(RAW.columns) | set(features.DERIVED_FEATURES) | set(features.SCREENING_SPEC) <= set(dic["variable"])
    assert not dic["variable"].duplicated().any()
    for col in ["transformacion", "imputacion", "encoding", "riesgo_leakage", "uso_final"]:
        assert dic[col].notna().all() and (dic[col].astype(str).str.len() > 0).all()
    tasa = dic[dic.variable == "annual_interest_rate_offer"].iloc[0]
    assert "Alto" in tasa["riesgo_leakage"] and "pricing" in tasa["uso_final"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("OK ", t.__name__)
    print(f"{len(tests)} pruebas aprobadas")
