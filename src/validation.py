"""Métricas de validación: PSI, AUC univariado (con dirección), pruebas de
significancia y test de aporte incremental.

Se usan para justificar el esquema temporal (6.2) y la pre-selección de
variables derivadas (6.3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


def psi(expected: pd.Series, actual: pd.Series, bins: int = 10, eps: float = 1e-4) -> float:
    """Population Stability Index con cortes por cuantiles de la muestra de referencia.

    Los faltantes forman su propio bin para que un cambio en la tasa de missing
    también se refleje en el indicador.
    """
    e = pd.Series(expected, dtype="float64")
    a = pd.Series(actual, dtype="float64")
    edges = np.unique(np.nanquantile(e, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf

    def dist(s):
        b = pd.cut(s, edges).cat.add_categories("missing").fillna("missing")
        return b.value_counts(normalize=True, sort=False)

    de, da = dist(e).clip(lower=eps), dist(a).clip(lower=eps)
    return float(((da - de) * np.log(da / de)).sum())


def psi_categorical(expected: pd.Series, actual: pd.Series, eps: float = 1e-4) -> float:
    """PSI para variables categóricas (cada categoría es un bin; NaN incluido)."""
    de = pd.Series(expected).fillna("missing").value_counts(normalize=True)
    da = pd.Series(actual).fillna("missing").value_counts(normalize=True)
    cats = de.index.union(da.index)
    de, da = de.reindex(cats, fill_value=0).clip(lower=eps), da.reindex(cats, fill_value=0).clip(lower=eps)
    return float(((da - de) * np.log(da / de)).sum())


def psi_label(value: float) -> str:
    if value < 0.10:
        return "Verde"
    return "Ámbar" if value < 0.25 else "Rojo"


def univariate_auc(y: pd.Series, x: pd.Series) -> float:
    """Magnitud del AUC univariado: max(AUC, 1 - AUC), imputando faltantes con la mediana.

    OJO: al "doblar" el AUC se pierde la dirección de la relación. Bajo ruido puro
    este valor ya promedia ~0.51 en DEV y ~0.52 en VAL, y un cambio de signo entre
    muestras pasa inadvertido. Para decidir sobre una variable usar `auc_test`,
    que conserva la dirección y entrega un p-valor.
    """
    x = pd.Series(x, dtype="float64")
    auc = roc_auc_score(y, x.fillna(x.median()))
    return max(auc, 1 - auc)


def auc_raw(y: pd.Series, x: pd.Series) -> float:
    """AUC sin doblar, descartando faltantes. > 0.5: a mayor valor, más default."""
    d = pd.DataFrame({"y": pd.Series(y).values, "x": pd.Series(x, dtype="float64").values}).dropna()
    return float(roc_auc_score(d["y"], d["x"]))


def auc_test(y: pd.Series, x: pd.Series) -> tuple[float, float]:
    """(AUC sin doblar, p-valor bilateral de H0: AUC = 0.5) mediante Mann-Whitney.

    El estadístico U de Mann-Whitney es exactamente AUC x n_malos x n_buenos, así
    que su prueba es la prueba natural de "¿esta variable ordena el riesgo?".
    """
    d = pd.DataFrame({"y": pd.Series(y).values, "x": pd.Series(x, dtype="float64").values}).dropna()
    malos, buenos = d.loc[d["y"] == 1, "x"], d.loc[d["y"] == 0, "x"]
    p = stats.mannwhitneyu(malos, buenos, alternative="two-sided").pvalue
    return float(roc_auc_score(d["y"], d["x"])), float(p)


def direction(auc: float) -> str:
    """'+' si la variable sube con el riesgo, '-' si baja."""
    return "+" if auc > 0.5 else "-"


def _design(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Matriz para los tests: winsorización p1-p99, mediana y estandarización (sobre df)."""
    z = df[cols].astype("float64").copy()
    for c in cols:
        lo, hi = z[c].quantile(0.01), z[c].quantile(0.99)
        z[c] = z[c].clip(lo, hi).fillna(z[c].median())
    sd = z.std(ddof=0).replace(0, 1.0)
    return (z - z.mean()) / sd


def _loglik(x: pd.DataFrame, y: np.ndarray) -> float:
    model = LogisticRegression(penalty=None, max_iter=5000).fit(x, y)
    p = np.clip(model.predict_proba(x)[:, 1], 1e-12, 1 - 1e-12)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def lr_test(df: pd.DataFrame, target: str, base_cols: list[str], add_cols: list[str]) -> float:
    """p-valor del test de razón de verosimilitud: ¿add_cols aporta sobre base_cols?

    Logit sin penalización ajustado sobre el mismo df para ambos modelos. Se usa
    con DEV para medir si una variable derivada agrega información a lo que ya
    contienen el núcleo de riesgo y sus propios componentes.
    """
    base = list(dict.fromkeys(base_cols))
    extra = [c for c in dict.fromkeys(add_cols) if c not in base]
    if not extra:
        return float("nan")
    y = df[target].to_numpy()
    stat = 2 * (_loglik(_design(df, base + extra), y) - _loglik(_design(df, base), y))
    return float(stats.chi2.sf(max(stat, 0.0), len(extra)))


def _quintile_dummies(df: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
    s = df[col].astype("float64")
    tramo = pd.qcut(s, q, duplicates="drop").astype(str).where(s.notna(), "faltante")
    return pd.get_dummies(tramo, prefix=col, drop_first=True).astype(float)


def lr_test_binned(df: pd.DataFrame, target: str, base_cols: list[str], add_cols: list[str], q: int = 5) -> float:
    """Como `lr_test`, pero con cada variable en tramos (quintiles + faltante), como la usaría un scorecard.

    Sirve para comprobar que una conclusión no depende de suponer una relación lineal.
    """
    base = list(dict.fromkeys(base_cols))
    extra = [c for c in dict.fromkeys(add_cols) if c not in base]
    if not extra:
        return float("nan")
    y = df[target].to_numpy()
    xb = pd.concat([_quintile_dummies(df, c, q) for c in base], axis=1)
    xa = pd.concat([xb] + [_quintile_dummies(df, c, q) for c in extra], axis=1)
    stat = 2 * (_loglik(xa, y) - _loglik(xb, y))
    return float(stats.chi2.sf(max(stat, 0.0), xa.shape[1] - xb.shape[1]))


def auc_standard_error(auc: float, n_pos: int, n_neg: int) -> float:
    """Error estándar de Hanley & McNeil (1982) para dimensionar muestras."""
    q1 = auc / (2 - auc)
    q2 = 2 * auc**2 / (1 + auc)
    var = (auc * (1 - auc) + (n_pos - 1) * (q1 - auc**2) + (n_neg - 1) * (q2 - auc**2)) / (n_pos * n_neg)
    return float(np.sqrt(var))


def gini(y: pd.Series, score: np.ndarray) -> float:
    """Gini = 2·AUC − 1, con el score orientado a riesgo (mayor = más default)."""
    return 2 * float(roc_auc_score(y, score)) - 1


def ks_statistic(y: pd.Series, score: np.ndarray) -> float:
    """Máxima distancia entre las distribuciones acumuladas de malos y buenos."""
    d = pd.DataFrame({"y": pd.Series(y).to_numpy(), "s": np.asarray(score, dtype=float)}).sort_values("s")
    cum_malos = (d["y"] == 1).cumsum() / max(1, (d["y"] == 1).sum())
    cum_buenos = (d["y"] == 0).cumsum() / max(1, (d["y"] == 0).sum())
    return float((cum_malos - cum_buenos).abs().max())


def paired_bootstrap_auc(y: pd.Series, score_a: np.ndarray, score_b: np.ndarray, n_boot: int = 1000,
                         seed: int = 42) -> dict:
    """Diferencia de AUC (a − b) sobre la misma muestra, con IC 95% por bootstrap pareado."""
    y = pd.Series(y).to_numpy()
    a, b = np.asarray(score_a, dtype=float), np.asarray(score_b, dtype=float)
    rng = np.random.default_rng(seed)
    diffs = []
    n = len(y)
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        if y[i].min() == y[i].max():
            continue
        diffs.append(roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i]))
    diffs = np.asarray(diffs)
    return {"delta_auc": float(roc_auc_score(y, a) - roc_auc_score(y, b)),
            "ic_inf": float(np.quantile(diffs, 0.025)), "ic_sup": float(np.quantile(diffs, 0.975))}
