"""Explicabilidad y fair lending (sección 6.8).

Dos bloques:

* **Explicabilidad.** Para el scorecard la explicación es exacta: los puntos que pierde
  cada característica frente a su mejor tramo suman la diferencia de score. Para el
  challenger de boosting se usa SHAP (TreeExplainer), que es la referencia del enunciado.
* **Fair lending.** No alcanza con "no usamos la variable": hay que medir si la decisión
  golpea distinto a grupos que el caso considera sensibles (territorio, ruralidad,
  informalidad, edad, hogar) y si el score funciona como proxy de ellos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from . import config as cfg
from .eda import wilson_ci

SENSIBLES = {
    "region": "Territorio",
    "cash_income_share": "Informalidad del ingreso",
    "distance_to_branch_km": "Ruralidad / distancia",
    "household_dependents": "Composición del hogar",
    "age": "Edad",
}


def _grupo(serie: pd.Series, cortes=None, etiquetas=None) -> pd.Series:
    if cortes is None:
        return serie.astype(str)
    return pd.cut(serie, cortes, labels=etiquetas).astype(str)


def adverse_impact_ratio(decision: pd.Series, grupo: pd.Series, favorable=("APPROVE",)) -> pd.DataFrame:
    """Tasa de decisión favorable por grupo y AIR contra el grupo más favorecido.

    Regla práctica de fair lending: AIR < 0.80 es la señal de alerta (regla de los 4/5).
    """
    d = pd.DataFrame({"grupo": grupo.astype(str).to_numpy(), "favorable": decision.isin(favorable).to_numpy()})
    t = d.groupby("grupo").agg(solicitudes=("favorable", "size"), favorables=("favorable", "sum"))
    t["tasa"] = t["favorables"] / t["solicitudes"]
    t["ic_inf"], t["ic_sup"] = wilson_ci(t["favorables"], t["solicitudes"])
    t["air"] = t["tasa"] / t["tasa"].max()
    t["alerta_4_5"] = t["air"] < 0.80
    return t.sort_values("tasa", ascending=False)


def error_rates_by_group(y: pd.Series, decision: pd.Series, grupo: pd.Series, favorable=("APPROVE",)) -> pd.DataFrame:
    """Errores por grupo sobre la población con resultado observado.

    * `buenos_no_aprobados`: buenos que la política no aprueba (costo para el cliente).
    * `malos_aprobados`: defaults que la política aprueba (costo para la entidad).
    Comparar estas tasas entre grupos es el análogo de "equal opportunity".
    """
    d = pd.DataFrame({"grupo": grupo.astype(str).to_numpy(), "y": pd.Series(y).to_numpy(),
                      "favorable": decision.isin(favorable).to_numpy()})
    filas = []
    for g, sub in d.groupby("grupo"):
        buenos, malos = sub[sub.y == 0], sub[sub.y == 1]
        filas.append({"grupo": g, "creditos": len(sub), "default_observado": sub.y.mean(),
                      "buenos_no_aprobados": 1 - buenos.favorable.mean() if len(buenos) else np.nan,
                      "malos_aprobados": malos.favorable.mean() if len(malos) else np.nan})
    return pd.DataFrame(filas).set_index("grupo")


def proxy_strength(X: pd.DataFrame, sensible: pd.Series, seed: int = cfg.SEED) -> dict:
    """¿Las variables del modelo permiten reconstruir el atributo sensible?

    Si no se puede predecir (AUC ~ 0.5 o R² ~ 0), el modelo no es un proxy encubierto.
    Se usa validación cruzada para no medir memorización.
    """
    X = X.astype(float).fillna(X.median(numeric_only=True))
    if sensible.dtype == object or str(sensible.dtype) in ("category", "string"):
        y = sensible.astype(str)
        aucs = []
        for clase in y.unique():
            objetivo = (y == clase).astype(int)
            if objetivo.sum() < 30:
                continue
            p = cross_val_predict(LogisticRegression(max_iter=5000), X, objetivo,
                                  cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba")[:, 1]
            aucs.append(roc_auc_score(objetivo, p))
        return {"tipo": "categórica", "auc_medio_cv": float(np.mean(aucs)), "auc_max_cv": float(np.max(aucs))}
    y = sensible.astype(float)
    pred = cross_val_predict(LinearRegression(), X, y, cv=5)
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {"tipo": "numérica", "r2_cv": float(1 - ss_res / ss_tot)}


def score_by_group(score: np.ndarray, pd_hat: np.ndarray, grupo: pd.Series) -> pd.DataFrame:
    """Distribución de score y PD por grupo (antes de cualquier regla de decisión)."""
    d = pd.DataFrame({"grupo": grupo.astype(str).to_numpy(), "score": np.asarray(score, dtype=float),
                      "pd": np.asarray(pd_hat, dtype=float)})
    t = d.groupby("grupo").agg(solicitudes=("score", "size"), score_medio=("score", "mean"),
                               score_p25=("score", lambda s: s.quantile(0.25)),
                               score_mediana=("score", "median"), pd_media=("pd", "mean"))
    return t.sort_values("score_medio", ascending=False)


def shap_global(modelo, X: pd.DataFrame, muestra: int = 1000, seed: int = cfg.SEED) -> pd.Series:
    """Importancia global: media de |SHAP| por variable (TreeExplainer)."""
    import shap

    X_s = X.sample(n=min(muestra, len(X)), random_state=seed)
    valores = shap.TreeExplainer(modelo).shap_values(X_s)
    if isinstance(valores, list):           # algunas versiones devuelven una matriz por clase
        valores = valores[1]
    return pd.Series(np.abs(valores).mean(axis=0), index=X.columns).sort_values(ascending=False)


def shap_local(modelo, X_fila: pd.DataFrame) -> pd.Series:
    """Aporte de cada variable al log-odds de una solicitud concreta."""
    import shap

    valores = shap.TreeExplainer(modelo).shap_values(X_fila)
    if isinstance(valores, list):
        valores = valores[1]
    return pd.Series(np.asarray(valores)[0], index=X_fila.columns).sort_values(key=np.abs, ascending=False)


def scorecard_local_explanation(card, fila: pd.DataFrame) -> pd.DataFrame:
    """Explicación exacta del scorecard: puntos obtenidos, máximo posible y puntos perdidos."""
    puntos = card.points_frame(fila).iloc[0]
    maximos = card.points_table().groupby("variable")["puntos"].max()
    t = pd.DataFrame({"puntos": puntos, "maximo_posible": maximos[card.variables]})
    t["puntos_perdidos"] = t["maximo_posible"] - t["puntos"]
    t["tramo"] = [card.binnings[v].labels()[i] if i >= 0 else "Faltante / no visto"
                  for v, i in ((v, card.binnings[v].bin_index(fila[v])[0]) for v in card.variables)]
    return t.sort_values("puntos_perdidos", ascending=False)
