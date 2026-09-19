"""Modelos PD y estrategia Champion/Challenger (sección 6.6).

Todos los candidatos comparten la misma población, la misma partición temporal y el
mismo preprocesamiento (el pipeline de 6.3, ajustado solo con DEV), para que la
comparación mida el algoritmo y no el tratamiento de datos.

El tuning se hace con **validación temporal dentro de DEV** (entrenar 2021 y validar
2022; entrenar 2021-2022 y validar 2023), como fija 6.2: nada se ajusta mirando VAL,
que se reserva para comparar modelos ya entrenados, y el OOT se abre una sola vez en 6.7.

Las grillas son chicas y con racional: profundidad baja, hojas con mínimo de casos y
regularización, porque con 351 defaults en DEV una búsqueda masiva encuentra ruido
(6.4 mostró que la señal vive en pocas variables).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

from . import config as cfg
from . import scorecard as sc
from . import validation

# Grillas pre-registradas (pequeñas y con racional; ver docstring)
GRIDS = {
    "Regresión logística (pipeline completo)": {"C": [0.05, 0.25, 1.0]},
    "Random Forest": {"max_depth": [4, 6], "min_samples_leaf": [20, 50], "max_features": ["sqrt", 0.5]},
    "XGBoost": {"max_depth": [2, 3], "n_estimators": [200, 400], "min_child_weight": [20, 50]},
    "LightGBM": {"num_leaves": [7, 15], "n_estimators": [200, 400], "min_child_samples": [30, 60]},
}

TIPO = {
    "Scorecard WOE (6.5)": "Lineal sobre 3 características en tramos",
    "Regresión logística (pipeline completo)": "Lineal sobre 32 columnas",
    "Random Forest": "Ensamble de árboles (bagging)",
    "XGBoost": "Boosting de árboles",
    "LightGBM": "Boosting de árboles",
    "LightGBM monótono": "Boosting con restricciones de monotonía",
}


def temporal_folds(dev: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    """Ventana expansiva dentro de DEV: (2021 -> 2022) y (2021-2022 -> 2023)."""
    anio = dev[cfg.DATE_COL].dt.year
    return [((anio <= 2021).to_numpy(), (anio == 2022).to_numpy()),
            ((anio <= 2022).to_numpy(), (anio == 2023).to_numpy())]


def monotone_vector(columns: list[str]) -> list[int]:
    """Restricción de monotonía por columna: +1 si el riesgo sube con la variable, -1 si baja, 0 si no se impone.

    Usa la dirección de negocio ya documentada en 6.5 (`scorecard.EXPECTED_TREND`).
    """
    signo = {"+": 1, "-": -1}
    return [signo.get(sc.EXPECTED_TREND.get(c) or "", 0) for c in columns]


@dataclass
class Candidato:
    nombre: str
    modelo: object
    params: dict
    columnas: list
    cv_gini: float
    predice: object   # callable(df) -> PD

    def pd_hat(self, df: pd.DataFrame) -> np.ndarray:
        return self.predice(df)


def _fit_predict(factory, params, X_tr, y_tr, X_te):
    m = factory(**params)
    m.fit(X_tr, y_tr)
    return m, m.predict_proba(X_te)[:, 1]


def tune(factory, grid: dict, X: pd.DataFrame, y: pd.Series, folds, fijos: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """Grid chica evaluada con los folds temporales; se elige por Gini medio fuera del fold."""
    fijos = fijos or {}
    combos = [dict(zip(grid, v)) for v in _product(grid.values())]
    filas = []
    for combo in combos:
        ginis = []
        for tr, te in folds:
            _, p = _fit_predict(factory, {**fijos, **combo}, X[tr], y[tr], X[te])
            ginis.append(2 * roc_auc_score(y[te], p) - 1)
        filas.append({**combo, "gini_fold_1": ginis[0], "gini_fold_2": ginis[1], "gini_cv": float(np.mean(ginis))})
    tabla = pd.DataFrame(filas).sort_values("gini_cv", ascending=False).reset_index(drop=True)
    mejores = {k: tabla.loc[0, k] for k in grid}
    mejores = {k: (int(v) if isinstance(v, (np.integer,)) else v) for k, v in mejores.items()}
    return mejores, tabla


def _product(valores):
    salida = [[]]
    for v in valores:
        salida = [fila + [x] for fila in salida for x in v]
    return salida


def columnas_vetadas(columnas: list[str]) -> list[str]:
    """Columnas de la matriz que corresponden a variables excluidas por fairness (6.5).

    Los challengers se entrenan con el mismo veto que el champion: si una variable no puede
    usarse por fairness en el scorecard, tampoco puede entrar por la puerta de atrás en un
    modelo de árboles.
    """
    vetadas = []
    for c in columnas:
        base = c.split("_")[0] if c.startswith(("region_", "channel_", "employment_type_")) else c
        if c in sc.EXCLUDED_BY_DESIGN or base in sc.EXCLUDED_BY_DESIGN or c.startswith("region_"):
            vetadas.append(c)
    return vetadas


def train_candidates(dev: pd.DataFrame, pipe, card: sc.Scorecard, binnings: dict,
                     target: str = cfg.TARGET, seed: int = cfg.SEED,
                     excluir_sensibles: bool = True) -> tuple[dict, dict]:
    """Entrena los candidatos de 6.6 y devuelve (candidatos, tablas de tuning)."""
    cols_in = [c for c in pipe.feature_names_in_] if hasattr(pipe, "feature_names_in_") else None
    X_dev = pipe.transform(dev[cols_in]) if cols_in else pipe.transform(dev)
    vetadas = columnas_vetadas(list(X_dev.columns)) if excluir_sensibles else []
    X_dev = X_dev.drop(columns=vetadas)
    y_dev = dev[target].to_numpy()
    folds = [(tr, te) for tr, te in temporal_folds(dev)]
    columnas = list(X_dev.columns)
    mono = monotone_vector(columnas)

    def matriz(df):
        X = pipe.transform(df[cols_in]) if cols_in else pipe.transform(df)
        return X.drop(columns=[c for c in vetadas if c in X.columns])

    candidatos, tuning = {}, {}

    # 1) Scorecard de 6.5: sin tuning, ya está ajustado con DEV.
    cv_sc = []
    for tr, te in folds:
        b_tr = {v: sc.fit_binning(dev[tr], v) for v in card.variables}
        c_tr, _ = sc.fit_scorecard(dev[tr], card.variables, b_tr)
        cv_sc.append(2 * roc_auc_score(y_dev[te], c_tr.predict_pd(dev[te])) - 1)
    candidatos["Scorecard WOE (6.5)"] = Candidato("Scorecard WOE (6.5)", card, {"variables": card.variables},
                                                  card.variables, float(np.mean(cv_sc)), card.predict_pd)

    # 2) Logística sobre el pipeline completo
    fac_lr = lambda **kw: LogisticRegression(max_iter=5000, **kw)
    mejor, tab = tune(fac_lr, GRIDS["Regresión logística (pipeline completo)"], X_dev, y_dev, folds)
    tuning["Regresión logística (pipeline completo)"] = tab
    m_lr = fac_lr(**mejor).fit(X_dev, y_dev)
    candidatos["Regresión logística (pipeline completo)"] = Candidato(
        "Regresión logística (pipeline completo)", m_lr, mejor, columnas, float(tab.loc[0, "gini_cv"]),
        lambda df, m=m_lr: m.predict_proba(matriz(df))[:, 1])

    # 3) Random Forest
    fac_rf = lambda **kw: RandomForestClassifier(n_estimators=400, random_state=seed, n_jobs=-1, **kw)
    mejor, tab = tune(fac_rf, GRIDS["Random Forest"], X_dev, y_dev, folds)
    tuning["Random Forest"] = tab
    m_rf = fac_rf(**mejor).fit(X_dev, y_dev)
    candidatos["Random Forest"] = Candidato("Random Forest", m_rf, mejor, columnas, float(tab.loc[0, "gini_cv"]),
                                            lambda df, m=m_rf: m.predict_proba(matriz(df))[:, 1])

    # 4) XGBoost
    fijos_xgb = dict(learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0,
                     eval_metric="logloss", random_state=seed, n_jobs=-1)
    fac_xgb = lambda **kw: XGBClassifier(**kw)
    mejor, tab = tune(fac_xgb, GRIDS["XGBoost"], X_dev, y_dev, folds, fijos=fijos_xgb)
    tuning["XGBoost"] = tab
    m_xgb = fac_xgb(**{**fijos_xgb, **mejor}).fit(X_dev, y_dev)
    candidatos["XGBoost"] = Candidato("XGBoost", m_xgb, mejor, columnas, float(tab.loc[0, "gini_cv"]),
                                      lambda df, m=m_xgb: m.predict_proba(matriz(df))[:, 1])

    # 5) LightGBM
    fijos_lgb = dict(learning_rate=0.05, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                     reg_lambda=5.0, random_state=seed, n_jobs=-1, verbose=-1)
    fac_lgb = lambda **kw: LGBMClassifier(**kw)
    mejor_lgb, tab = tune(fac_lgb, GRIDS["LightGBM"], X_dev, y_dev, folds, fijos=fijos_lgb)
    tuning["LightGBM"] = tab
    m_lgb = fac_lgb(**{**fijos_lgb, **mejor_lgb}).fit(X_dev, y_dev)
    candidatos["LightGBM"] = Candidato("LightGBM", m_lgb, mejor_lgb, columnas, float(tab.loc[0, "gini_cv"]),
                                       lambda df, m=m_lgb: m.predict_proba(matriz(df))[:, 1])

    # 6) LightGBM con restricciones de monotonía (misma configuración, dirección de negocio impuesta)
    cv_mono = []
    for tr, te in folds:
        _, p = _fit_predict(fac_lgb, {**fijos_lgb, **mejor_lgb, "monotone_constraints": mono},
                            X_dev[tr], y_dev[tr], X_dev[te])
        cv_mono.append(2 * roc_auc_score(y_dev[te], p) - 1)
    m_mono = fac_lgb(**{**fijos_lgb, **mejor_lgb, "monotone_constraints": mono}).fit(X_dev, y_dev)
    candidatos["LightGBM monótono"] = Candidato("LightGBM monótono", m_mono, {**mejor_lgb, "monotone_constraints": "6.5"},
                                                columnas, float(np.mean(cv_mono)),
                                                lambda df, m=m_mono: m.predict_proba(matriz(df))[:, 1])
    return candidatos, tuning


def latency_ms(candidato: Candidato, df: pd.DataFrame, repeticiones: int = 5) -> float:
    """Milisegundos para puntuar 1,000 solicitudes, incluyendo el preprocesamiento."""
    muestra = df.sample(n=min(1000, len(df)), random_state=cfg.SEED)
    tiempos = []
    for _ in range(repeticiones):
        t0 = time.perf_counter()
        candidato.pd_hat(muestra)
        tiempos.append((time.perf_counter() - t0) * 1000)
    return float(np.median(tiempos))


def comparison_table(candidatos: dict, muestras: dict, target: str = cfg.TARGET) -> pd.DataFrame:
    """Compara discriminación, calibración, estabilidad y complejidad operativa.

    `muestras` debe traer DEV y VAL (el OOT se abre recién en 6.7).
    """
    from . import evaluation as ev

    dev, val = muestras["DEV"], muestras["VAL"]
    filas = []
    for nombre, c in candidatos.items():
        p_dev, p_val = c.pd_hat(dev), c.pd_hat(val)
        disc_dev, disc_val = ev.discrimination(dev[target], p_dev), ev.discrimination(val[target], p_val)
        cal_val = ev.calibration_metrics(val[target], p_val)
        gini_anio = [2 * roc_auc_score(g[target], c.pd_hat(g)) - 1
                     for _, g in dev.groupby(dev[cfg.DATE_COL].dt.year)]
        filas.append({
            "modelo": nombre, "tipo": TIPO.get(nombre, ""),
            "variables": len(c.columnas),
            "gini_dev": disc_dev["gini"], "gini_cv_temporal": c.cv_gini, "gini_val": disc_val["gini"],
            "ks_val": disc_val["ks"], "brier_val": cal_val["brier"],
            "observado_sobre_predicho_val": cal_val["observado_sobre_predicho"],
            "calibracion_pendiente_val": cal_val["calibracion_pendiente"],
            "brecha_dev_menos_val": disc_dev["gini"] - disc_val["gini"],
            "rango_gini_por_anio_dev": max(gini_anio) - min(gini_anio),
            "psi_pd_dev_val": validation.psi(pd.Series(p_dev), pd.Series(p_val)),
            "latencia_ms_1000": latency_ms(c, val),
        })
    return pd.DataFrame(filas).set_index("modelo")


def champion_challenger(comparacion: pd.DataFrame, candidatos: dict, val: pd.DataFrame,
                        orden_simplicidad: list[str], target: str = cfg.TARGET, n_boot: int = 1000) -> pd.DataFrame:
    """Regla pre-registrada: gana el modelo **más simple** cuya discriminación fuera de muestra
    no sea significativamente peor que la del mejor (bootstrap pareado en VAL, IC 95%).

    Devuelve la comparación contra el mejor Gini de VAL, con la diferencia y su intervalo.
    """
    mejor = comparacion["gini_val"].idxmax()
    p_mejor = candidatos[mejor].pd_hat(val)
    filas = []
    for nombre in orden_simplicidad:
        if nombre not in candidatos:
            continue
        dif = validation.paired_bootstrap_auc(val[target], candidatos[nombre].pd_hat(val), p_mejor,
                                              n_boot=n_boot, seed=cfg.SEED)
        filas.append({"modelo": nombre, "simplicidad": orden_simplicidad.index(nombre) + 1,
                      "gini_val": comparacion.loc[nombre, "gini_val"],
                      "delta_auc_vs_mejor": dif["delta_auc"], "ic_inf": dif["ic_inf"], "ic_sup": dif["ic_sup"],
                      "peor_de_forma_significativa": dif["ic_sup"] < 0})
    t = pd.DataFrame(filas).set_index("modelo")
    t.attrs["mejor_gini_val"] = mejor
    return t
