"""Métricas de validación y calibración de la PD (sección 6.7).

Separa dos preguntas que se confunden a menudo:

* **Discriminación** (¿ordena bien?): AUC, Gini, KS, lift/gains, deciles.
* **Calibración** (¿el nivel es correcto?): PD predicha vs. default observado, Brier,
  error de calibración y la recta de calibración (intercepto y pendiente).

Un modelo puede ordenar perfecto y estar mal calibrado, que es justo lo que pasa aquí
cuando el nivel de riesgo se desplaza entre cosechas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score, roc_curve

from . import config as cfg
from .eda import wilson_ci

EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def discrimination(y, pd_hat) -> dict:
    """AUC, Gini y KS."""
    y = pd.Series(y).to_numpy()
    pd_hat = np.asarray(pd_hat, dtype=float)
    auc = roc_auc_score(y, pd_hat)
    fpr, tpr, _ = roc_curve(y, pd_hat)
    return {"auc": float(auc), "gini": float(2 * auc - 1), "ks": float(np.max(tpr - fpr))}


def classification_metrics(y, pd_hat, threshold: float) -> dict:
    """Precisión, recall, F1 y matriz de confusión en un punto de operación.

    "Positivo" = el modelo marca la solicitud como riesgosa (PD >= umbral), que en la
    política equivale a no aprobarla automáticamente.
    """
    y = pd.Series(y).to_numpy()
    pred = (np.asarray(pd_hat, dtype=float) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    precision = tp / (tp + fp) if tp + fp else np.nan
    recall = tp / (tp + fn) if tp + fn else np.nan
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else np.nan
    return {"umbral_pd": float(threshold), "marcados": int(tp + fp), "precision": float(precision),
            "recall": float(recall), "f1": float(f1), "exactitud": float((tp + tn) / len(y)),
            "vp": int(tp), "fp": int(fp), "fn": int(fn), "vn": int(tn)}


def confusion_frame(y, pd_hat, threshold: float) -> pd.DataFrame:
    y = pd.Series(y).to_numpy()
    pred = (np.asarray(pd_hat, dtype=float) >= threshold).astype(int)
    m = confusion_matrix(y, pred, labels=[0, 1])
    return pd.DataFrame(m, index=["Bueno observado", "Default observado"],
                        columns=["Modelo: no marca", "Modelo: marca riesgo"])


def decile_table(y, pd_hat, n: int = 10) -> pd.DataFrame:
    """Deciles de riesgo (1 = más riesgoso) con lift, ganancia acumulada y KS por decil."""
    d = pd.DataFrame({"y": pd.Series(y).to_numpy(), "pd": np.asarray(pd_hat, dtype=float)})
    d["decil"] = pd.qcut(d["pd"].rank(method="first", ascending=False), n, labels=range(1, n + 1)).astype(int)
    t = d.groupby("decil").agg(creditos=("y", "size"), defaults=("y", "sum"), pd_media=("pd", "mean"))
    t["default_rate"] = t["defaults"] / t["creditos"]
    t["ic_inf"], t["ic_sup"] = wilson_ci(t["defaults"], t["creditos"])
    tasa_global = d["y"].mean()
    t["lift"] = t["default_rate"] / tasa_global
    t["buenos"] = t["creditos"] - t["defaults"]
    t["captura_malos_acum"] = t["defaults"].cumsum() / t["defaults"].sum()
    t["captura_buenos_acum"] = t["buenos"].cumsum() / t["buenos"].sum()
    t["poblacion_acum"] = t["creditos"].cumsum() / t["creditos"].sum()
    t["lift_acumulado"] = (t["defaults"].cumsum() / t["creditos"].cumsum()) / tasa_global
    t["ks_acumulado"] = t["captura_malos_acum"] - t["captura_buenos_acum"]
    return t


def calibration_table(y, pd_hat, bins=10, edges=None) -> pd.DataFrame:
    """PD predicha vs. default observado por tramo de PD, con IC y razón observado/predicho."""
    y = pd.Series(y).to_numpy()
    p = np.asarray(pd_hat, dtype=float)
    grupo = (pd.cut(pd.Series(p), edges) if edges is not None
             else pd.qcut(pd.Series(p).rank(method="first"), bins, labels=range(1, bins + 1)))
    d = pd.DataFrame({"g": grupo.astype(str).to_numpy(), "y": y, "p": p})
    t = d.groupby("g", sort=False).agg(creditos=("y", "size"), defaults=("y", "sum"),
                                       pd_predicha=("p", "mean"), default_observado=("y", "mean"))
    t = t.sort_values("pd_predicha")
    t["ic_inf"], t["ic_sup"] = wilson_ci(t["defaults"], t["creditos"])
    t["observado_sobre_predicho"] = t["default_observado"] / t["pd_predicha"]
    t["dentro_del_ic"] = (t["pd_predicha"] >= t["ic_inf"]) & (t["pd_predicha"] <= t["ic_sup"])
    t.index.name = "tramo_pd"
    return t


def calibration_metrics(y, pd_hat, bins: int = 10) -> dict:
    """Brier, error de calibración esperado (ECE), razón observado/predicho y recta de calibración.

    La recta de calibración (Cox): logit(observado) = a + b x logit(predicho). Un modelo
    calibrado tiene a = 0 y b = 1; a distinto de 0 es un problema de nivel y b distinto
    de 1, de pendiente (la corrección necesita ambos parámetros, no solo el intercepto).
    """
    y = pd.Series(y).to_numpy().astype(float)
    p = np.clip(np.asarray(pd_hat, dtype=float), EPS, 1 - EPS)
    brier = float(np.mean((p - y) ** 2))
    tasa = y.mean()
    brier_ref = float(np.mean((tasa - y) ** 2))
    t = calibration_table(y, p, bins=bins)
    ece = float((t["creditos"] / t["creditos"].sum() * (t["default_observado"] - t["pd_predicha"]).abs()).sum())
    m = LogisticRegression(penalty=None, max_iter=5000).fit(_logit(p).reshape(-1, 1), y.astype(int))
    return {"brier": brier, "brier_skill": float(1 - brier / brier_ref), "ece": ece,
            "pd_media_predicha": float(p.mean()), "default_observado": float(tasa),
            "observado_sobre_predicho": float(tasa / p.mean()),
            "calibracion_intercepto": float(m.intercept_[0]), "calibracion_pendiente": float(m.coef_[0][0])}


class PlattCalibrator:
    """Recalibración logística sobre el log-odds del modelo: ajusta nivel (a) y pendiente (b)."""

    def fit(self, pd_hat, y):
        self.model_ = LogisticRegression(penalty=None, max_iter=5000).fit(
            _logit(pd_hat).reshape(-1, 1), pd.Series(y).to_numpy())
        self.intercept_ = float(self.model_.intercept_[0])
        self.slope_ = float(self.model_.coef_[0][0])
        return self

    def transform(self, pd_hat) -> np.ndarray:
        return self.model_.predict_proba(_logit(pd_hat).reshape(-1, 1))[:, 1]

    def to_dict(self) -> dict:
        return {"metodo": "platt", "intercepto": self.intercept_, "pendiente": self.slope_}


class IsotonicCalibrator:
    """Recalibración isotónica: no impone forma, pero necesita más datos y puede escalonar."""

    def fit(self, pd_hat, y):
        self.model_ = IsotonicRegression(out_of_bounds="clip", y_min=EPS, y_max=1 - EPS).fit(
            np.asarray(pd_hat, dtype=float), pd.Series(y).to_numpy())
        return self

    def transform(self, pd_hat) -> np.ndarray:
        return self.model_.predict(np.asarray(pd_hat, dtype=float))

    def to_dict(self) -> dict:
        return {"metodo": "isotonica", "n_tramos": int(len(np.unique(self.model_.y_thresholds_)))}


def full_report(y, pd_hat, threshold: float, bins: int = 10) -> dict:
    """Todas las métricas mínimas que pide 6.7 en un solo diccionario."""
    out = discrimination(y, pd_hat)
    out.update(calibration_metrics(y, pd_hat, bins=bins))
    out.update(classification_metrics(y, pd_hat, threshold))
    return out


def threshold_for_approval(pd_hat, approval_rate: float) -> float:
    """Umbral de PD que deja aprobada esa proporción de la muestra (punto de operación)."""
    return float(np.quantile(np.asarray(pd_hat, dtype=float), approval_rate))
