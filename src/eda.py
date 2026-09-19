"""EDA orientado a riesgo (sección 6.4).

Regla de uso de muestras (coherente con 6.2 y 6.3):
* Las relaciones variable-riesgo que informan decisiones se miden en DEV (2021-2023).
* VAL (2024) se muestra para ver si el hallazgo se sostiene fuera de DEV; no decide.
* La cosecha OOT (2025) no se abre variable por variable: se reserva para la evaluación final.
  Solo se usan sus agregados de cartera ya publicados en 6.1-6.2 y métricas sin target (PSI).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression

from . import config as cfg


def wilson_ci(k: np.ndarray, n: np.ndarray, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """Intervalo de Wilson para una proporción (se comporta bien con tasas bajas y n chico)."""
    k, n = np.asarray(k, dtype=float), np.asarray(n, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(n > 0, k / n, np.nan)
        den = 1 + z**2 / n
        centro = (p + z**2 / (2 * n)) / den
        margen = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return np.clip(centro - margen, 0.0, 1.0), np.clip(centro + margen, 0.0, 1.0)


def quantile_edges(s: pd.Series, q: int) -> np.ndarray:
    """Cortes por cuantiles (únicos) con extremos abiertos, para aplicar los mismos cortes a otra muestra."""
    e = np.unique(np.nanquantile(pd.Series(s, dtype="float64"), np.linspace(0, 1, q + 1)))
    e[0], e[-1] = -np.inf, np.inf
    return e


def bad_rate_table(df: pd.DataFrame, col: str, edges=None, target: str = cfg.TARGET) -> pd.DataFrame:
    """Tasa de default por tramo (o categoría) con IC de Wilson; el faltante va como tramo propio."""
    if edges is not None:
        tramo = pd.cut(df[col], edges).astype(str).where(df[col].notna(), "Faltante")
    else:
        tramo = df[col].astype(str).where(df[col].notna(), "Faltante")
    t = df.groupby(tramo, sort=False)[target].agg(creditos="size", defaults="sum")
    if edges is not None:
        orden = [str(i) for i in pd.cut(pd.Series(dtype=float), edges).cat.categories] + ["Faltante"]
        t = t.reindex([o for o in orden if o in t.index])
    else:
        t = t.sort_index()
    t["pct_creditos"] = t["creditos"] / t["creditos"].sum()
    t["default_rate"] = t["defaults"] / t["creditos"]
    t["ic_inf"], t["ic_sup"] = wilson_ci(t["defaults"], t["creditos"])
    t.index.name = "tramo"
    return t


def compare_samples(samples: dict, col: str, q: int | None = None, edges=None, target: str = cfg.TARGET) -> pd.DataFrame:
    """Tasa de default por tramo en varias muestras usando los cortes de la primera (DEV)."""
    ref = next(iter(samples.values()))
    if edges is None and q is not None:
        edges = quantile_edges(ref[col], q)
    out = []
    for name, d in samples.items():
        t = bad_rate_table(d, col, edges, target)[["creditos", "default_rate", "ic_inf", "ic_sup"]]
        out.append(t.add_prefix(f"{name.lower()}_"))
    return pd.concat(out, axis=1)


def bh_fdr(pvalues) -> np.ndarray:
    """q-valores de Benjamini-Hochberg (tasa de falsos descubrimientos)."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    orden = np.argsort(p)
    q = p[orden] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1].clip(max=1.0)
    out = np.empty(m)
    out[orden] = q
    return out


def univariate_screening(dev: pd.DataFrame, val: pd.DataFrame, numeric: list[str], categorical: list[str],
                         target: str = cfg.TARGET, alpha: float = 0.05) -> pd.DataFrame:
    """Asociación de cada candidata con el default en DEV, corregida por comparaciones múltiples.

    Numéricas: AUC con dirección y Mann-Whitney. Categóricas: chi-cuadrado.
    VAL se reporta como información (¿se mantiene la dirección?).
    """
    from . import validation

    filas = []
    for c in numeric:
        auc, p = validation.auc_test(dev[target], dev[c])
        auc_v = validation.auc_raw(val[target], val[c])
        filas.append({"variable": c, "tipo": "numérica", "auc_dev": auc, "p_dev": p, "auc_val_info": auc_v,
                      "misma_direccion_en_val": (auc > 0.5) == (auc_v > 0.5)})
    for c in categorical:
        p = stats.chi2_contingency(pd.crosstab(dev[c], dev[target]))[1]
        p_v = stats.chi2_contingency(pd.crosstab(val[c], val[target]))[1]
        filas.append({"variable": c, "tipo": "categórica", "auc_dev": np.nan, "p_dev": p, "auc_val_info": np.nan,
                      "misma_direccion_en_val": np.nan, "p_val_info": p_v})
    t = pd.DataFrame(filas)
    t["q_bh"] = bh_fdr(t["p_dev"])
    t["senal_en_dev"] = t["q_bh"] < alpha
    return t.sort_values("p_dev").reset_index(drop=True)


def _loglik(X: pd.DataFrame, y: np.ndarray) -> float:
    m = LogisticRegression(penalty=None, max_iter=5000).fit(X, y)
    p = np.clip(m.predict_proba(X)[:, 1], 1e-12, 1 - 1e-12)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def interaction_test(df: pd.DataFrame, a: str, b: str, q: int = 3, target: str = cfg.TARGET) -> dict:
    """¿El efecto de `a` depende del nivel de `b`? Terciles (faltante aparte) y test de razón de verosimilitud."""
    d = df.copy()
    ta = pd.qcut(d[a], q, labels=[f"{a}_T{i+1}" for i in range(q)]).astype(str).where(d[a].notna(), f"{a}_falt")
    tb = pd.qcut(d[b], q, labels=[f"{b}_T{i+1}" for i in range(q)]).astype(str).where(d[b].notna(), f"{b}_falt")
    completos = d[a].notna() & d[b].notna()
    d, ta, tb = d[completos], ta[completos], tb[completos]
    Za = pd.get_dummies(ta, drop_first=True).astype(float)
    Zb = pd.get_dummies(tb, drop_first=True).astype(float)
    base = pd.concat([Za, Zb], axis=1)
    inter = pd.DataFrame({f"{x}*{z}": Za[x] * Zb[z] for x in Za.columns for z in Zb.columns}, index=d.index)
    y = d[target].to_numpy()
    stat = 2 * (_loglik(pd.concat([base, inter], axis=1), y) - _loglik(base, y))
    matriz = d.groupby([ta, tb])[target].mean().unstack()
    n = d.groupby([ta, tb])[target].size().unstack()
    return {"p_interaccion": float(stats.chi2.sf(max(stat, 0), inter.shape[1])), "gl": int(inter.shape[1]),
            "default_rate": matriz, "creditos": n}


def level_shift_test(dev: pd.DataFrame, val: pd.DataFrame, score_col: str, target: str = cfg.TARGET) -> dict:
    """¿Entre DEV y VAL cambió el nivel de riesgo (intercepto) o la capacidad de ordenar (pendiente)?"""
    d = pd.concat([dev.assign(_val=0.0), val.assign(_val=1.0)])
    mu, sd = dev[score_col].mean(), dev[score_col].std()
    z = (d[score_col].fillna(dev[score_col].median()) - mu) / sd
    X1 = pd.DataFrame({"z": z})
    X2 = X1.assign(val=d["_val"].to_numpy())
    X3 = X2.assign(z_val=X2["z"] * X2["val"])
    y = d[target].to_numpy()
    l1, l2, l3 = _loglik(X1, y), _loglik(X2, y), _loglik(X3, y)
    m2 = LogisticRegression(penalty=None, max_iter=5000).fit(X2, y)
    m3 = LogisticRegression(penalty=None, max_iter=5000).fit(X3, y)
    return {"cambio_log_odds": float(m2.coef_[0][1]), "odds_ratio_val": float(np.exp(m2.coef_[0][1])),
            "p_nivel": float(stats.chi2.sf(2 * (l2 - l1), 1)),
            "pendiente_dev": float(m3.coef_[0][0]), "cambio_pendiente": float(m3.coef_[0][2]),
            "p_pendiente": float(stats.chi2.sf(2 * (l3 - l2), 1))}


def cohort_trend(df: pd.DataFrame, date_col: str = cfg.DATE_COL, target: str = cfg.TARGET,
                 step_date: str = "2023-01-01") -> tuple[pd.DataFrame, dict]:
    """Tasa de default por cohorte trimestral con IC, tendencia lineal en log-odds y prueba de escalón."""
    d = df.copy()
    trimestre = d[date_col].dt.to_period("Q")
    t = d.groupby(trimestre)[target].agg(creditos="size", defaults="sum")
    t["default_rate"] = t["defaults"] / t["creditos"]
    t["ic_inf"], t["ic_sup"] = wilson_ci(t["defaults"], t["creditos"])
    idx = (d[date_col].dt.year - d[date_col].dt.year.min()) * 4 + d[date_col].dt.quarter - 1
    y = d[target].to_numpy()
    p0 = y.mean()
    l0 = float(np.sum(y * np.log(p0) + (1 - y) * np.log(1 - p0)))
    Xt = pd.DataFrame({"t": idx.to_numpy(dtype=float)})
    Xs = pd.DataFrame({"escalon": (d[date_col] >= step_date).to_numpy(dtype=float)})
    lt, ls, lts = _loglik(Xt, y), _loglik(Xs, y), _loglik(pd.concat([Xt, Xs], axis=1), y)
    mt = LogisticRegression(penalty=None, max_iter=5000).fit(Xt, y)
    resumen = {"odds_ratio_anual": float(np.exp(4 * mt.coef_[0][0])), "p_tendencia": float(stats.chi2.sf(2 * (lt - l0), 1)),
               "p_escalon_sobre_tendencia": float(stats.chi2.sf(2 * (lts - lt), 1)),
               "p_tendencia_sobre_escalon": float(stats.chi2.sf(2 * (lts - ls), 1))}
    return t, resumen


def gap_by_year(df: pd.DataFrame, flag: pd.Series, date_col: str = cfg.DATE_COL, target: str = cfg.TARGET) -> pd.DataFrame:
    """Diferencia de default (con flag - sin flag) por año de originación."""
    d = df.assign(_flag=pd.Series(flag, index=df.index).astype(int), _anio=df[date_col].dt.year)
    t = d.groupby(["_anio", "_flag"])[target].agg(["size", "mean"]).unstack()
    out = pd.DataFrame({"creditos_con": t[("size", 1)], "default_con": t[("mean", 1)],
                        "creditos_sin": t[("size", 0)], "default_sin": t[("mean", 0)]})
    out["brecha_pp"] = (out["default_con"] - out["default_sin"]) * 100
    out["p_fisher"] = [stats.fisher_exact(pd.crosstab(g["_flag"], g[target]).to_numpy())[1] for _, g in d.groupby("_anio")]
    out.index.name = "anio"
    return out


def segment_map(df: pd.DataFrame, segments: dict, target: str = cfg.TARGET) -> pd.DataFrame:
    """Composición y riesgo por segmento: participación en créditos y monto, default y pérdida realizada."""
    d = df.assign(_perdida=df["ead_at_default"].fillna(0) * df["lgd_observed"].fillna(0))
    filas = []
    for nombre, serie in segments.items():
        g = d.groupby(pd.Series(serie, index=d.index).astype(str))
        t = g.agg(creditos=(target, "size"), defaults=(target, "sum"), monto=("requested_amount", "sum"),
                  perdida=("_perdida", "sum"))
        t["segmentacion"] = nombre
        filas.append(t.reset_index(names="segmento"))
    out = pd.concat(filas, ignore_index=True)
    out["pct_creditos"] = out["creditos"] / len(d)
    out["pct_monto"] = out["monto"] / d["requested_amount"].sum()
    out["default_rate"] = out["defaults"] / out["creditos"]
    out["ic_inf"], out["ic_sup"] = wilson_ci(out["defaults"], out["creditos"])
    out["perdida_sobre_monto"] = out["perdida"] / out["monto"]
    return out[["segmentacion", "segmento", "creditos", "pct_creditos", "pct_monto", "default_rate", "ic_inf",
                "ic_sup", "perdida_sobre_monto"]]


def loss_decomposition(df: pd.DataFrame, date_col: str = cfg.DATE_COL, target: str = cfg.TARGET) -> pd.DataFrame:
    """Pérdida realizada / monto = frecuencia x exposición x severidad, por año."""
    d = df.assign(_anio=df[date_col].dt.year, _perdida=df["ead_at_default"].fillna(0) * df["lgd_observed"].fillna(0))
    dd = d[d[target] == 1].assign(_ead_ratio=lambda x: x["ead_at_default"] / x["requested_amount"])
    out = pd.DataFrame({
        "default_rate": d.groupby("_anio")[target].mean(),
        "ead_sobre_monto_default": dd.groupby("_anio")["_ead_ratio"].mean(),
        "lgd_media": dd.groupby("_anio")["lgd_observed"].mean(),
        "perdida_sobre_monto": d.groupby("_anio")["_perdida"].sum() / d.groupby("_anio")["requested_amount"].sum(),
    })
    out.index.name = "anio"
    return out


def loss_concentration(df: pd.DataFrame, col: str, edges, labels: list[str], target: str = cfg.TARGET) -> pd.DataFrame:
    """Participación de cada tramo en créditos, defaults y pérdida realizada (curva de concentración).

    Los cortes se pasan explícitos (en el notebook, los de DEV) para comparar muestras con los mismos tramos.
    """
    tramo = pd.cut(df[col], edges, labels=labels).astype(str).where(df[col].notna(), "Faltante")
    perdida = df["ead_at_default"].fillna(0) * df["lgd_observed"].fillna(0)
    t = pd.DataFrame({
        "creditos": df.groupby(tramo).size(),
        "defaults": df.groupby(tramo)[target].sum(),
        "monto": df.groupby(tramo)["requested_amount"].sum(),
        "perdida": perdida.groupby(tramo).sum(),
    }).reindex([l for l in labels + ["Faltante"] if l in set(tramo)])
    t["pct_creditos"] = t["creditos"] / t["creditos"].sum()
    t["default_rate"] = t["defaults"] / t["creditos"]
    t["pct_defaults"] = t["defaults"] / t["defaults"].sum()
    t["pct_perdida"] = t["perdida"] / t["perdida"].sum()
    t["pct_perdida_acumulada"] = t["pct_perdida"].cumsum()
    t.index.name = "tramo"
    return t
