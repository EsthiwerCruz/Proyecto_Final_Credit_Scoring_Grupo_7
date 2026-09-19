"""Estimación de EAD y LGD (secciones 6.10 y 6.11).

El producto es un **microcrédito amortizable sin garantía**: no hay línea, ni saldo
utilizado, ni monto no utilizado, así que `ccf_observed` viene vacío y **no corresponde
forzar un CCF revolvente**, como advierte la nota del caso. La exposición se modela como
un **factor sobre el monto desembolsado**:

    ead_ratio = ead_at_default / requested_amount

y la severidad como la LGD observada, acotada en [0, 1]:

    lgd = (EAD − recuperaciones + costos de recuperación) / EAD

Ambas son variables acotadas, así que el modelo estadístico natural es una **logística
fraccional** (Papke-Wooldridge): la misma verosimilitud binomial aplicada a una respuesta
continua entre 0 y 1, que se estima duplicando cada observación con pesos (y, 1−y). Así la
predicción nunca se sale del rango, a diferencia de una regresión lineal.

Todo se ajusta con los defaults de **DEV**, se compara en **VAL** y el OOT se reserva.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression

from . import config as cfg

EPS = 1e-6


def build_severity_frame(fx: pd.DataFrame, target: str = cfg.TARGET) -> pd.DataFrame:
    """Población de 6.10 y 6.11: créditos en default con exposición y recuperación informadas."""
    d = fx[fx[target].eq(1)].copy()
    d["ead_ratio"] = d["ead_at_default"] / d["requested_amount"]
    d["recuperacion_sobre_ead"] = d["recovery_amount_total"] / d["ead_at_default"]
    d["costo_sobre_ead"] = d["recovery_cost_total"] / d["ead_at_default"]
    d["lgd"] = d["lgd_observed"]
    return d


def implied_month_on_book(df: pd.DataFrame, annual_rate=None) -> np.ndarray:
    """Mes de vida del crédito implícito en la exposición, según el calendario francés.

    Para un crédito con n cuotas y tasa mensual r, el saldo tras k pagos es
    B_k / P = (1 − (1+r)^(k−n)) / (1 − (1+r)^(−n)). Despejando k se obtiene cuántas cuotas
    tendría que haber pagado el cliente para llegar a esa exposición. Es un control de
    coherencia: con default a 12 meses, k debería ser menor o igual a 12.
    """
    tasa = (df["annual_interest_rate_offer"].to_numpy(dtype=float) if annual_rate is None
            else np.full(len(df), float(annual_rate)))
    r = (1 + tasa) ** (1 / 12) - 1
    n = df["term_months"].to_numpy(dtype=float)
    ratio = (df["ead_at_default"] / df["requested_amount"]).to_numpy(dtype=float)
    den = 1 - (1 + r) ** (-n)
    arg = np.clip(1 - ratio * den, EPS, None)
    return n + np.log(arg) / np.log(1 + r)


# ---------------------------------------------------------------------------
# Baseline segmentado
# ---------------------------------------------------------------------------
class SegmentedBaseline:
    """Promedio por segmento, con los cortes aprendidos en DEV.

    Es el punto de comparación obligatorio del enunciado: cualquier modelo tiene que
    demostrar que le gana a "usar el promedio del segmento". Si un segmento tiene menos
    de `min_n` casos, se le asigna el promedio global (credibilidad insuficiente).
    """

    def __init__(self, columnas: list[str] | None = None, cortes: dict | None = None, min_n: int = 30):
        self.columnas = columnas or []
        self.cortes = cortes or {}
        self.min_n = min_n

    def _segmento(self, df: pd.DataFrame) -> pd.Series:
        if not self.columnas:
            return pd.Series(["global"] * len(df), index=df.index)
        partes = []
        for c in self.columnas:
            if c in self.cortes:
                partes.append(pd.cut(df[c], self.cortes[c]).astype(str))
            else:
                partes.append(df[c].astype(str))
        return pd.Series([" | ".join(v) for v in zip(*[p.to_numpy() for p in partes])], index=df.index)

    def fit(self, df: pd.DataFrame, y: str):
        seg = self._segmento(df)
        t = df.groupby(seg)[y].agg(["size", "mean"])
        self.global_ = float(df[y].mean())
        self.tabla_ = t.assign(usado=np.where(t["size"] >= self.min_n, t["mean"], self.global_))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        seg = self._segmento(df)
        return seg.map(self.tabla_["usado"]).fillna(self.global_).to_numpy(dtype=float)

    def table(self) -> pd.DataFrame:
        return self.tabla_.rename(columns={"size": "casos", "mean": "promedio_observado", "usado": "estimacion"})


# ---------------------------------------------------------------------------
# Modelos para variable acotada
# ---------------------------------------------------------------------------
class FractionalLogit:
    """Logística fraccional (Papke-Wooldridge) para respuestas continuas en [0, 1].

    Se estima duplicando cada observación con pesos (y, 1−y): la verosimilitud resultante
    es la quasi-binomial, así que los coeficientes son los de la logística fraccional y la
    predicción queda acotada por construcción.
    """

    def __init__(self, columnas: list[str], C: float = 1.0):
        self.columnas = columnas
        self.C = C

    def _X(self, df: pd.DataFrame) -> np.ndarray:
        x = df[self.columnas].astype(float)
        x = x.fillna(self.mediana_ if hasattr(self, "mediana_") else x.median())
        return ((x - self.mu_) / self.sd_).to_numpy() if hasattr(self, "mu_") else x.to_numpy()

    def fit(self, df: pd.DataFrame, y: str):
        x = df[self.columnas].astype(float)
        self.mediana_ = x.median()
        x = x.fillna(self.mediana_)
        self.mu_, self.sd_ = x.mean(), x.std(ddof=0).replace(0, 1.0)
        X = ((x - self.mu_) / self.sd_).to_numpy()
        yy = np.clip(df[y].to_numpy(dtype=float), EPS, 1 - EPS)
        X2 = np.vstack([X, X])
        y2 = np.r_[np.ones(len(X)), np.zeros(len(X))]
        w2 = np.r_[yy, 1 - yy]
        self.modelo_ = LogisticRegression(penalty="l2", C=self.C, max_iter=5000).fit(X2, y2, sample_weight=w2)
        self.coef_ = pd.Series(self.modelo_.coef_[0], index=self.columnas)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.modelo_.predict_proba(self._X(df))[:, 1]


class BoundedGBM:
    """Alternativa de ML: boosting sobre la respuesta acotada, con predicción recortada a [0, 1]."""

    def __init__(self, columnas: list[str], **kw):
        self.columnas = columnas
        self.kw = dict(max_depth=2, learning_rate=0.05, max_iter=200, min_samples_leaf=40,
                       l2_regularization=1.0, random_state=cfg.SEED) | kw

    def fit(self, df: pd.DataFrame, y: str):
        self.modelo_ = HistGradientBoostingRegressor(**self.kw).fit(df[self.columnas], df[y])
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.clip(self.modelo_.predict(df[self.columnas]), 0.0, 1.0)


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------
def evaluate(y_true, y_pred) -> dict:
    """Error, sesgo y ajuste. El sesgo importa tanto como el error: una estimación sesgada
    hacia abajo subestima la pérdida esperada de toda la cartera."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    err = p - y
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {"n": int(len(y)), "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "sesgo": float(np.mean(err)), "sesgo_relativo": float(np.mean(err) / y.mean()),
            "r2": float(1 - ss_res / ss_tot), "media_observada": float(y.mean()), "media_predicha": float(p.mean())}


def error_by_segment(df: pd.DataFrame, y: str, pred: np.ndarray, segmento: pd.Series) -> pd.DataFrame:
    """Error y sesgo por segmento: donde el sesgo cambia de signo hay heterogeneidad no capturada."""
    d = pd.DataFrame({"seg": segmento.astype(str).to_numpy(), "y": df[y].to_numpy(dtype=float),
                      "p": np.asarray(pred, dtype=float)})
    t = d.groupby("seg").apply(lambda g: pd.Series({
        "casos": len(g), "observado": g["y"].mean(), "estimado": g["p"].mean(),
        "sesgo": (g["p"] - g["y"]).mean(), "mae": (g["p"] - g["y"]).abs().mean()}))
    return t.sort_values("casos", ascending=False)


def lgd_economica(df: pd.DataFrame, tasa_descuento: float) -> np.ndarray:
    """LGD económica: descuenta las recuperaciones por el tiempo de workout.

    La LGD contable del archivo suma soles de distintos momentos. Con un workout de ~12
    meses, descontar cambia el resultado de forma material, y es lo que piden Basilea e
    IFRS 9 (descontar a la tasa efectiva del contrato).
    """
    factor = (1 + tasa_descuento) ** (df["months_to_recovery"].to_numpy(dtype=float) / 12)
    ead = df["ead_at_default"].to_numpy(dtype=float)
    rec = df["recovery_amount_total"].to_numpy(dtype=float)
    costo = df["recovery_cost_total"].to_numpy(dtype=float)
    return np.clip((ead - rec / factor + costo) / ead, 0.0, 1.0)


def downturn_lgd(df: pd.DataFrame, columna: str = "lgd", fecha: str = cfg.DATE_COL) -> dict:
    """LGD de downturn: la peor cosecha observada, que es el insumo del escenario de stress."""
    por_anio = df.groupby(df[fecha].dt.year)[columna].mean()
    return {"promedio_largo_plazo": float(df[columna].mean()), "peor_cosecha": float(por_anio.max()),
            "anio_peor_cosecha": int(por_anio.idxmax()), "recargo_downturn": float(por_anio.max() - df[columna].mean())}
