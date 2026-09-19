"""Scorecard tradicional (sección 6.5): binning, WOE/IV, selección, logística y escala de puntos.

Todo lo que "aprende" del dato se ajusta con DEV. VAL solo se usa para comparar un
conjunto pre-registrado de especificaciones (como fija 6.2) y el OOT no se consulta.

Convenciones
------------
* WOE = ln(%buenos / %malos): WOE alto = menos riesgo. La logística modela P(default),
  así que todos los coeficientes deben ser NEGATIVOS; uno positivo delata colinealidad.
* Tramos numéricos cerrados a la derecha: (-inf, c1], (c1, c2], ..., (ck, +inf).
* Faltante: tramo propio con WOE neutral (0) por diseño, porque en 6.3 los faltantes
  resultaron compatibles con MCAR y el efecto del score faltante no fue estable.
* Categorías no vistas en DEV: WOE neutral.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression, LogisticRegression

from . import config as cfg
from . import validation

# --- Parámetros del binning y de la selección (fijados antes de ver resultados) ---
N_PREBINS = 20             # clasificación fina: cuantiles
BIN_MIN_SHARE = 0.05       # cada tramo con al menos 5% de DEV
BIN_MIN_BADS = 15          # y al menos 15 defaults
BIN_MAX = 6                # como máximo 6 tramos (sin contar faltante)
# Fusión adicional de tramos adyacentes sin diferencia significativa: DESACTIVADA (None).
# Se evaluó con validación temporal dentro de DEV (ajuste 2021-2022, prueba 2023): con alfa 0.05
# el scorecard quedaba en 22 puntajes distintos y Gini 0.395 en 2023; sin esa fusión, con los
# mismos mínimos de tamaño, defaults y monotonía, 112 puntajes y Gini 0.433, con el orden de los
# tramos intacto en 2023. Los mínimos de tamaño ya protegen la estabilidad (notebook 03, §2).
BIN_MERGE_ALPHA = None
MIN_WOE_GAP = 0.05         # tramos adyacentes con log-odds casi iguales (|diferencia| < 0.05) se fusionan: separarlos no aporta
WOE_SMOOTHING = 0.5        # suavizado de Laplace para tramos pequeños
IV_MIN = 0.02              # poder mínimo (convención)
IV_PERM_ALPHA = 0.05       # y además distinto de un binning ajustado sobre ruido
IV_PERMUTATIONS = 200
WOE_CORR_MAX = 0.60        # redundancia entre características (Spearman sobre WOE)
VIF_MAX = 2.5
PSI_MAX = 0.10
COEF_ALPHA = 0.05

# --- Escala de puntos ---
BASE_SCORE = 600
BASE_ODDS = 10.0           # buenos:malos en el puntaje base (DEV tiene ~8.8:1)
PDO = 20

# Dirección esperada del riesgo: "+" sube con el valor, "-" baja; None = se toma la de DEV.
EXPECTED_TREND = {
    "bureau_score": "-", "dti": "+", "dti_post": "+", "prior_delinquencies_24m": "+",
    "monthly_debt_payment": "+", "bureau_inquiries_6m": "+", "active_loans": "+",
    "savings_balance": "-", "ahorro_sobre_monto": "-", "monthly_income": "-",
    "employment_tenure_months": "-", "relationship_months": "-", "new_customer_flag": "+",
    "requested_amount": None, "term_months": None, "age": None, "household_dependents": None,
    "distance_to_branch_km": None, "cash_income_share": None,
}

# Variables que no entran al scorecard por diseño (fairness): posibles proxies sin necesidad de negocio.
EXCLUDED_BY_DESIGN = {
    "age": "Edad: característica protegida en la práctica crediticia; solo entraría con necesidad de negocio demostrada.",
    "region": "Proxy territorial: el caso exige fairness territorial.",
    "distance_to_branch_km": "Proxy territorial y de ruralidad: penalizarla contradice crecer fuera de agencias.",
    "household_dependents": "Proxy de composición del hogar.",
    "cash_income_share": "Proxy de informalidad: el caso pide no excluir por falta de trazabilidad bancaria.",
}

REASON_TEXT_MISSING = {
    "bureau_score": "Score de buró no disponible (re-consultar)",
    "dti": "Ingreso no informado: capacidad de pago no verificable",
    "dti_post": "Ingreso no informado: capacidad de pago no verificable",
    "ahorro_sobre_monto": "Saldo de ahorro no informado",
    "savings_balance": "Saldo de ahorro no informado",
}

REASON_TEXT = {
    "bureau_score": "Score de buró bajo",
    "dti": "Carga de deuda alta frente al ingreso",
    "dti_post": "Carga de deuda post-crédito alta frente al ingreso",
    "prior_delinquencies_24m": "Moras previas en los últimos 24 meses",
    "monthly_debt_payment": "Cuota de deudas vigentes alta",
    "ahorro_sobre_monto": "Ahorro bajo frente al monto solicitado",
    "savings_balance": "Ahorro bajo",
    "bureau_inquiries_6m": "Muchas consultas recientes al buró",
    "new_customer_flag": "Sin relación previa con la Caja",
}


# =============================================================================
# Binning
# =============================================================================
def _woe(goods: np.ndarray, bads: np.ndarray, total_goods: float, total_bads: float) -> np.ndarray:
    k = len(goods)
    dg = (goods + WOE_SMOOTHING) / (total_goods + WOE_SMOOTHING * k)
    db = (bads + WOE_SMOOTHING) / (total_bads + WOE_SMOOTHING * k)
    return np.log(dg / db)


def _pair_pvalue(n1, b1, n2, b2) -> float:
    tabla = np.array([[b1, n1 - b1], [b2, n2 - b2]])
    if (tabla.sum(axis=0) == 0).any():
        return 1.0
    return float(stats.chi2_contingency(tabla, correction=False)[1])


@dataclass
class Binning:
    """Tramos de una característica y su WOE (ajustados con DEV)."""
    variable: str
    kind: str                                   # "numeric" | "categorical"
    edges: list = field(default_factory=list)   # numérica: cortes interiores
    groups: list = field(default_factory=list)  # categórica: grupos de categorías
    woe: list = field(default_factory=list)     # WOE por tramo (sin faltante)
    woe_missing: float = 0.0
    trend: str | None = None

    # ---- asignación de tramos ----
    def bin_index(self, x: pd.Series) -> np.ndarray:
        """Índice de tramo; -1 = faltante o categoría no vista."""
        s = pd.Series(x)
        if self.kind == "numeric":
            v = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
            idx = np.searchsorted(np.asarray(self.edges, dtype=float), v, side="left")
            idx[np.isnan(v)] = -1
            return idx
        lookup = {c: i for i, g in enumerate(self.groups) for c in g}
        return s.map(lambda c: lookup.get(c, -1) if pd.notna(c) else -1).to_numpy(dtype=int)

    def labels(self) -> list[str]:
        if self.kind == "numeric":
            cortes = [-np.inf] + list(self.edges) + [np.inf]
            fmt = (lambda v: f"{v:,.4g}")
            return [f"({fmt(a)}, {fmt(b)}]" if np.isfinite(a) and np.isfinite(b)
                    else (f"<= {fmt(b)}" if not np.isfinite(a) else f"> {fmt(a)}")
                    for a, b in zip(cortes[:-1], cortes[1:])]
        return [" / ".join(map(str, g)) for g in self.groups]

    def transform(self, x: pd.Series) -> np.ndarray:
        idx = self.bin_index(x)
        w = np.asarray(self.woe, dtype=float)
        return np.where(idx >= 0, w[np.clip(idx, 0, len(w) - 1)], self.woe_missing)

    def table(self, x: pd.Series, y: pd.Series) -> pd.DataFrame:
        """Tabla por tramo (incluye faltante) con n, defaults, tasa, WOE e IV."""
        idx = self.bin_index(x)
        yy = pd.Series(y).to_numpy()
        etiquetas = self.labels()
        filas = []
        for i, lab in enumerate(etiquetas + ["Faltante / no visto"]):
            m = idx == (i if i < len(etiquetas) else -1)
            n, b = int(m.sum()), int(yy[m].sum())
            if i == len(etiquetas) and n == 0:
                continue
            filas.append({"variable": self.variable, "tramo": lab, "orden": i if i < len(etiquetas) else -1,
                          "creditos": n, "defaults": b, "buenos": n - b,
                          "woe": self.woe[i] if i < len(etiquetas) else self.woe_missing})
        t = pd.DataFrame(filas)
        t["pct_creditos"] = t["creditos"] / t["creditos"].sum()
        t["default_rate"] = t["defaults"] / t["creditos"].where(t["creditos"] > 0)
        dg = t["buenos"] / t["buenos"].sum()
        db = t["defaults"] / t["defaults"].sum()
        t["iv_tramo"] = (dg - db) * t["woe"]
        return t

    def iv(self, x: pd.Series, y: pd.Series) -> float:
        return float(self.table(x, y)["iv_tramo"].sum())

    def to_dict(self) -> dict:
        return {"variable": self.variable, "kind": self.kind, "edges": [float(e) for e in self.edges],
                "groups": self.groups, "woe": [float(w) for w in self.woe],
                "woe_missing": float(self.woe_missing), "trend": self.trend}

    @classmethod
    def from_dict(cls, d: dict) -> "Binning":
        return cls(**d)


def _merge(stats_: list[dict], i: int) -> list[dict]:
    """Fusiona el tramo i con el i+1."""
    a, b = stats_[i], stats_[i + 1]
    fusion = {"n": a["n"] + b["n"], "bads": a["bads"] + b["bads"], "keys": a["keys"] + b["keys"]}
    return stats_[:i] + [fusion] + stats_[i + 2:]


def _coarse_classing(stats_: list[dict], trend: str | None, n_total: int,
                     merge_alpha: float | None = None, bin_max: int = BIN_MAX) -> list[dict]:
    """Aplica tamaño mínimo, tendencia monótona, tope de tramos y (opcional) fusión por significancia."""
    br = lambda s: s["bads"] / s["n"] if s["n"] else 0.0
    min_n = BIN_MIN_SHARE * n_total
    # 1) tamaño mínimo y defaults mínimos
    while len(stats_) > 1:
        malos = [i for i, s in enumerate(stats_) if s["n"] < min_n or s["bads"] < BIN_MIN_BADS]
        if not malos:
            break
        i = min(malos, key=lambda k: stats_[k]["n"])
        if i == 0:
            j = 0
        elif i == len(stats_) - 1:
            j = i - 1
        else:
            j = i - 1 if abs(br(stats_[i - 1]) - br(stats_[i])) <= abs(br(stats_[i + 1]) - br(stats_[i])) else i
        stats_ = _merge(stats_, j)
    # 2) tendencia monótona en la dirección esperada
    if trend in ("+", "-"):
        while len(stats_) > 1:
            viol = [i for i in range(len(stats_) - 1)
                    if (br(stats_[i]) > br(stats_[i + 1]) if trend == "+" else br(stats_[i]) < br(stats_[i + 1]))]
            if not viol:
                break
            i = min(viol, key=lambda k: abs(br(stats_[k]) - br(stats_[k + 1])))
            stats_ = _merge(stats_, i)
    # 3) tramos adyacentes prácticamente iguales en riesgo
    lo = lambda st: np.log((st["bads"] + WOE_SMOOTHING) / (st["n"] - st["bads"] + WOE_SMOOTHING))
    while len(stats_) > 1:
        gaps = [abs(lo(stats_[i]) - lo(stats_[i + 1])) for i in range(len(stats_) - 1)]
        i = int(np.argmin(gaps))
        if gaps[i] < MIN_WOE_GAP:
            stats_ = _merge(stats_, i)
        else:
            break
    # 4) tope de tramos y, si está activa, fusión de adyacentes sin diferencia significativa
    while len(stats_) > 1:
        ps = [_pair_pvalue(stats_[i]["n"], stats_[i]["bads"], stats_[i + 1]["n"], stats_[i + 1]["bads"])
              for i in range(len(stats_) - 1)]
        i = int(np.argmax(ps))
        if len(stats_) > bin_max or (merge_alpha is not None and ps[i] > merge_alpha):
            stats_ = _merge(stats_, i)
        else:
            break
    return stats_


def fit_numeric_binning(x: pd.Series, y: pd.Series, variable: str, trend: str | None = "auto",
                        merge_alpha: float | None = BIN_MERGE_ALPHA, bin_max: int = BIN_MAX) -> Binning:
    s = pd.to_numeric(pd.Series(x), errors="coerce")
    yy = pd.Series(y).to_numpy()
    m = s.notna().to_numpy()
    v, t = s.to_numpy()[m], yy[m]
    if trend == "auto" or trend is None:
        rho = stats.spearmanr(v, t)[0] if len(np.unique(v)) > 1 else 0.0
        trend = "+" if rho > 0 else "-"
    uniq = np.unique(v)
    if len(uniq) <= 12:
        cortes = uniq[:-1]
    else:
        cortes = np.unique(np.quantile(v, np.linspace(0, 1, N_PREBINS + 1))[1:-1])
    idx = np.searchsorted(cortes, v, side="left")
    stats_ = [{"n": int((idx == i).sum()), "bads": int(t[idx == i].sum()), "keys": [i]}
              for i in range(len(cortes) + 1)]
    stats_ = [s_ for s_ in stats_ if s_["n"] > 0]
    stats_ = _coarse_classing(stats_, trend, n_total=len(yy), merge_alpha=merge_alpha, bin_max=bin_max)
    # cortes finales: el límite superior de cada tramo salvo el último
    edges = [float(cortes[max(s_["keys"])]) for s_ in stats_[:-1]]
    idx_f = np.searchsorted(np.asarray(edges), v, side="left")
    goods = np.array([((idx_f == i) & (t == 0)).sum() for i in range(len(edges) + 1)], dtype=float)
    bads = np.array([((idx_f == i) & (t == 1)).sum() for i in range(len(edges) + 1)], dtype=float)
    woe = _woe(goods, bads, float((yy == 0).sum()), float((yy == 1).sum()))
    return Binning(variable, "numeric", edges=edges, woe=list(woe), woe_missing=0.0, trend=trend)


def fit_categorical_binning(x: pd.Series, y: pd.Series, variable: str,
                            merge_alpha: float | None = BIN_MERGE_ALPHA, bin_max: int = BIN_MAX) -> Binning:
    s = pd.Series(x)
    yy = pd.Series(y).to_numpy()
    m = s.notna().to_numpy()
    d = pd.DataFrame({"c": s[m].astype(str).to_numpy(), "y": yy[m]})
    g = d.groupby("c")["y"].agg(["size", "sum"])
    g = g.assign(br=g["sum"] / g["size"]).sort_values("br")
    stats_ = [{"n": int(r["size"]), "bads": int(r["sum"]), "keys": [c]} for c, r in g.iterrows()]
    stats_ = _coarse_classing(stats_, trend="+", n_total=len(yy), merge_alpha=merge_alpha, bin_max=bin_max)  # ordenadas por tasa
    groups = [s_["keys"] for s_ in stats_]
    goods = np.array([s_["n"] - s_["bads"] for s_ in stats_], dtype=float)
    bads = np.array([s_["bads"] for s_ in stats_], dtype=float)
    woe = _woe(goods, bads, float((yy == 0).sum()), float((yy == 1).sum()))
    return Binning(variable, "categorical", groups=groups, woe=list(woe), woe_missing=0.0, trend=None)


def fit_binning(df: pd.DataFrame, variable: str, target: str = cfg.TARGET,
                merge_alpha: float | None = BIN_MERGE_ALPHA, bin_max: int = BIN_MAX) -> Binning:
    if df[variable].dtype == object or str(df[variable].dtype) in ("category", "string", "str"):
        return fit_categorical_binning(df[variable], df[target], variable, merge_alpha, bin_max)
    return fit_numeric_binning(df[variable], df[target], variable, EXPECTED_TREND.get(variable, "auto") or "auto",
                               merge_alpha, bin_max)


def iv_permutation_pvalue(df: pd.DataFrame, variable: str, iv_obs: float, n_perm: int = IV_PERMUTATIONS,
                          seed: int = cfg.SEED, target: str = cfg.TARGET) -> float:
    """p-valor del IV contra binnings ajustados con el target permutado (mismas reglas).

    El binning óptimo "busca" separación, así que sobre ruido también produce IV > 0;
    esta prueba descuenta ese sesgo de selección.
    """
    rng = np.random.default_rng(seed)
    y = df[target].to_numpy()
    mayores = 0
    for _ in range(n_perm):
        yp = pd.Series(rng.permutation(y), index=df.index)
        d = df[[variable]].assign(**{target: yp})
        b = fit_binning(d, variable, target)
        if b.iv(d[variable], yp) >= iv_obs:
            mayores += 1
    return (1 + mayores) / (1 + n_perm)


def iv_label(iv: float) -> str:
    if iv < 0.02:
        return "Sin poder"
    if iv < 0.10:
        return "Débil"
    if iv < 0.30:
        return "Medio"
    return "Fuerte" if iv <= 0.50 else "Muy fuerte (revisar leakage)"


# =============================================================================
# Diagnósticos de selección
# =============================================================================
def bin_psi(binning: Binning, ref: pd.Series, other: pd.Series) -> float:
    """PSI sobre la distribución de tramos (incluye faltante). No usa el target."""
    a = pd.Series(binning.bin_index(ref)).value_counts(normalize=True)
    b = pd.Series(binning.bin_index(other)).value_counts(normalize=True)
    k = a.index.union(b.index)
    a, b = a.reindex(k, fill_value=0).clip(lower=1e-4), b.reindex(k, fill_value=0).clip(lower=1e-4)
    return float(((b - a) * np.log(b / a)).sum())


def trend_holds(binning: Binning, sub_a: pd.DataFrame, sub_b: pd.DataFrame, target: str = cfg.TARGET) -> bool:
    """El tramo de más riesgo (menor WOE) incumple más que el de menos riesgo en ambos subperiodos."""
    if len(binning.woe) < 2:
        return False
    lo, hi = int(np.argmin(binning.woe)), int(np.argmax(binning.woe))
    for d in (sub_a, sub_b):
        idx = binning.bin_index(d[binning.variable])
        y = d[target].to_numpy()
        if (idx == lo).sum() == 0 or (idx == hi).sum() == 0 or y[idx == lo].mean() <= y[idx == hi].mean():
            return False
    return True


def vif(frame: pd.DataFrame) -> pd.Series:
    out = {}
    for c in frame.columns:
        otras = frame.drop(columns=c)
        if otras.shape[1] == 0:
            out[c] = 1.0
            continue
        r2 = LinearRegression().fit(otras, frame[c]).score(otras, frame[c])
        out[c] = 1.0 / max(1e-12, 1.0 - r2)
    return pd.Series(out)


def fit_logit(X: pd.DataFrame, y: pd.Series, sample_weight: np.ndarray | None = None) -> pd.DataFrame:
    """Logística sin penalización con errores estándar de Wald (información de Fisher)."""
    m = LogisticRegression(penalty=None, max_iter=10000).fit(X, y, sample_weight=sample_weight)
    X1 = np.column_stack([np.ones(len(X)), X.to_numpy()])
    p = m.predict_proba(X)[:, 1]
    w = p * (1 - p) * (sample_weight if sample_weight is not None else 1.0)
    cov = np.linalg.inv(X1.T @ (X1 * w[:, None]))
    beta = np.concatenate([m.intercept_, m.coef_[0]])
    se = np.sqrt(np.diag(cov))
    z = beta / se
    return pd.DataFrame({"coef": beta, "se": se, "z": z, "p_value": 2 * stats.norm.sf(np.abs(z))},
                        index=["intercepto"] + list(X.columns))


# =============================================================================
# Scorecard
# =============================================================================
@dataclass
class Scorecard:
    binnings: dict
    variables: list
    intercept: float
    coefs: dict
    base_score: float = BASE_SCORE
    base_odds: float = BASE_ODDS
    pdo: float = PDO
    meta: dict = field(default_factory=dict)

    @property
    def factor(self) -> float:
        return self.pdo / np.log(2)

    @property
    def offset(self) -> float:
        return self.base_score - self.factor * np.log(self.base_odds)

    def woe_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({v: self.binnings[v].transform(df[v]) for v in self.variables}, index=df.index)

    def log_odds_bad(self, df: pd.DataFrame) -> np.ndarray:
        w = self.woe_frame(df)
        return self.intercept + sum(self.coefs[v] * w[v].to_numpy() for v in self.variables)

    def predict_pd(self, df: pd.DataFrame) -> np.ndarray:
        """PD de desarrollo (nivel de DEV). La recalibración al nivel reciente se hace en 6.7."""
        return 1.0 / (1.0 + np.exp(-self.log_odds_bad(df)))

    def points_table(self) -> pd.DataFrame:
        n = len(self.variables)
        filas = []
        for v in self.variables:
            b = self.binnings[v]
            for i, (lab, w) in enumerate(list(zip(b.labels(), b.woe)) + [("Faltante / no visto", b.woe_missing)]):
                puntos = -(self.coefs[v] * w + self.intercept / n) * self.factor + self.offset / n
                filas.append({"variable": v, "tramo": lab, "orden": i if i < len(b.woe) else -1,
                              "woe": w, "coef": self.coefs[v], "puntos_exactos": puntos, "puntos": int(round(puntos))})
        return pd.DataFrame(filas)

    def points_frame(self, df: pd.DataFrame, exact: bool = False) -> pd.DataFrame:
        pt = self.points_table()
        col = "puntos_exactos" if exact else "puntos"
        out = {}
        for v in self.variables:
            tab = pt[pt.variable == v].set_index("orden")[col]
            idx = self.binnings[v].bin_index(df[v])
            out[v] = tab.reindex(idx).to_numpy()
        return pd.DataFrame(out, index=df.index)

    def score(self, df: pd.DataFrame, exact: bool = False) -> np.ndarray:
        return self.points_frame(df, exact).sum(axis=1).to_numpy()

    def score_to_pd(self, score) -> np.ndarray:
        """PD implícita en la escala (calibración de desarrollo)."""
        return 1.0 / (1.0 + np.exp((np.asarray(score, dtype=float) - self.offset) / self.factor))

    def reason_codes(self, df: pd.DataFrame, n: int = 3) -> list[list[str]]:
        """Características que más puntos le restan a cada solicitud frente al mejor tramo.

        Si el dato falta, la razón lo dice (no es lo mismo "score bajo" que "sin score").
        """
        pf = self.points_frame(df)
        maximos = self.points_table().groupby("variable")["puntos"].max()
        perdidos = maximos[self.variables].to_numpy() - pf.to_numpy()
        faltante = np.column_stack([self.binnings[v].bin_index(df[v]) < 0 for v in self.variables])
        out = []
        for fila, falt in zip(perdidos, faltante):
            orden = np.argsort(-fila)
            out.append([(REASON_TEXT_MISSING if falt[k] else REASON_TEXT).get(self.variables[k], self.variables[k])
                        for k in orden[:n] if fila[k] > 0])
        return out

    def to_dict(self) -> dict:
        return {"variables": self.variables, "intercept": float(self.intercept),
                "coefs": {k: float(v) for k, v in self.coefs.items()},
                "base_score": self.base_score, "base_odds": self.base_odds, "pdo": self.pdo,
                "binnings": {v: self.binnings[v].to_dict() for v in self.variables}, "meta": self.meta}

    @classmethod
    def from_dict(cls, d: dict) -> "Scorecard":
        return cls(binnings={k: Binning.from_dict(b) for k, b in d["binnings"].items()}, variables=d["variables"],
                   intercept=d["intercept"], coefs=d["coefs"], base_score=d["base_score"],
                   base_odds=d["base_odds"], pdo=d["pdo"], meta=d.get("meta", {}))

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Scorecard":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def fit_scorecard(dev: pd.DataFrame, variables: list[str], binnings: dict, target: str = cfg.TARGET,
                  sample_weight: np.ndarray | None = None, meta: dict | None = None) -> tuple[Scorecard, pd.DataFrame]:
    """Ajusta la logística sobre WOE con los tramos ya fijados y devuelve el scorecard y sus coeficientes."""
    W = pd.DataFrame({v: binnings[v].transform(dev[v]) for v in variables}, index=dev.index)
    coefs = fit_logit(W, dev[target], sample_weight)
    sc = Scorecard(binnings={v: binnings[v] for v in variables}, variables=list(variables),
                   intercept=float(coefs.loc["intercepto", "coef"]),
                   coefs={v: float(coefs.loc[v, "coef"]) for v in variables}, meta=meta or {})
    return sc, coefs


def fuzzy_augmentation(accepts: pd.DataFrame, rejects: pd.DataFrame, scorecard: Scorecard,
                       inflation: float = 1.0, target: str = cfg.TARGET) -> tuple[pd.DataFrame, np.ndarray]:
    """Reject inference por aumentación difusa: cada rechazado entra como bueno y como malo
    con pesos (1 - p, p), donde p = min(0.95, inflación x PD del modelo de aceptados)."""
    p = np.clip(inflation * scorecard.predict_pd(rejects), 0.0, 0.95)
    malos = rejects.assign(**{target: 1})
    buenos = rejects.assign(**{target: 0})
    datos = pd.concat([accepts, malos, buenos], ignore_index=True)
    pesos = np.concatenate([np.ones(len(accepts)), p, 1 - p])
    return datos, pesos


# =============================================================================
# Selección de características (pre-registrada)
# =============================================================================
SELECTION_CRITERIA = {
    "S1": f"Poder en DEV: IV >= {IV_MIN}",
    "S2": f"El IV no es un artefacto del binning: prueba de permutación con las mismas reglas, p < {IV_PERM_ALPHA}",
    "S3": "Dirección del riesgo con sentido de negocio documentado (tendencia esperada) o categórica",
    "S4": "El tramo de más riesgo supera al de menos riesgo en 2021-2022 y en 2023 (estable dentro de DEV)",
    "S5": f"Distribución de tramos estable: PSI DEV->VAL y DEV->OOT < {PSI_MAX} (sin target)",
    "S6": "No se invierte en VAL: con los tramos y WOE de DEV, el tramo de más riesgo sigue incumpliendo más que el de menos riesgo y el IV medido en VAL es positivo",
    "S7": "No está excluida por diseño (fairness: proxy sin necesidad de negocio)",
}


def univariate_selection(dev: pd.DataFrame, val: pd.DataFrame, oot: pd.DataFrame, candidates: list[str],
                         n_perm: int = IV_PERMUTATIONS, target: str = cfg.TARGET) -> tuple[pd.DataFrame, dict]:
    """Binning en DEV y criterios S1-S7 para cada candidata. OOT solo aporta el PSI (sin target)."""
    sub = [dev[dev[cfg.DATE_COL].between(pd.Timestamp(a), pd.Timestamp(b))] for a, b in cfg.DEV_SUBPERIODS.values()]
    filas, binnings = [], {}
    for v in candidates:
        b = fit_binning(dev, v, target)
        binnings[v] = b
        iv = b.iv(dev[v], dev[target])
        lo, hi = (int(np.argmin(b.woe)), int(np.argmax(b.woe))) if len(b.woe) > 1 else (0, 0)
        idx_v, yv = b.bin_index(val[v]), val[target].to_numpy()
        iv_val = b.iv(val[v], val[target])
        s6 = (len(b.woe) > 1 and (idx_v == lo).sum() > 0 and (idx_v == hi).sum() > 0
              and yv[idx_v == lo].mean() > yv[idx_v == hi].mean() and iv_val > 0)
        psi_val, psi_oot = bin_psi(b, dev[v], val[v]), bin_psi(b, dev[v], oot[v])
        p_perm = iv_permutation_pvalue(dev, v, iv, n_perm, target=target) if iv >= IV_MIN else np.nan
        es_cat = b.kind == "categorical"
        fila = {"variable": v, "tipo": "categórica" if es_cat else "numérica", "tramos": len(b.woe),
                "iv_dev": iv, "poder": iv_label(iv), "p_permutacion": p_perm,
                "tendencia": b.trend if not es_cat else "por categoría", "psi_val": psi_val, "psi_oot": psi_oot,
                "iv_val_info": iv_val,
                "S1": iv >= IV_MIN,
                "S2": bool(iv >= IV_MIN and p_perm < IV_PERM_ALPHA),
                "S3": es_cat or EXPECTED_TREND.get(v) in ("+", "-"),
                "S4": trend_holds(b, *sub, target=target),
                "S5": max(psi_val, psi_oot) < PSI_MAX,
                "S6": bool(s6),
                "S7": v not in EXCLUDED_BY_DESIGN}
        filas.append(fila)
    t = pd.DataFrame(filas)
    crit = list(SELECTION_CRITERIA)
    t["pasa"] = t[crit].all(axis=1)
    t["no_cumple"] = t[crit].apply(lambda r: ", ".join(c for c in crit if not r[c]), axis=1)
    return t.sort_values("iv_dev", ascending=False).reset_index(drop=True), binnings


def woe_frame(df: pd.DataFrame, binnings: dict, variables: list[str]) -> pd.DataFrame:
    return pd.DataFrame({v: binnings[v].transform(df[v]) for v in variables}, index=df.index)


def forward_stepwise(dev: pd.DataFrame, binnings: dict, candidates: list[str], alpha: float = COEF_ALPHA,
                     vif_max: float = VIF_MAX, target: str = cfg.TARGET) -> pd.DataFrame:
    """Selección hacia adelante en DEV: entra la que más mejora la verosimilitud si su test de razón de
    verosimilitud tiene p < alpha, todos los coeficientes quedan negativos y significativos y el VIF < vif_max."""
    y = dev[target].to_numpy()
    W = woe_frame(dev, binnings, candidates)
    elegidas, pasos = [], []
    p0 = y.mean()
    ll_actual = float(np.sum(y * np.log(p0) + (1 - y) * np.log(1 - p0)))
    while True:
        mejor = None
        for v in [c for c in candidates if c not in elegidas]:
            X = W[elegidas + [v]]
            ll = validation._loglik(X, y)
            p = float(stats.chi2.sf(max(2 * (ll - ll_actual), 0), 1))
            if p >= alpha:
                continue
            coefs = fit_logit(X, dev[target])
            ok_signo = (coefs.drop(index="intercepto")["coef"] < 0).all()
            ok_p = (coefs.drop(index="intercepto")["p_value"] < alpha).all()
            vmax = float(vif(X).max()) if X.shape[1] > 1 else 1.0
            if ok_signo and ok_p and vmax < vif_max and (mejor is None or ll > mejor[1]):
                mejor = (v, ll, p, vmax)
        if mejor is None:
            break
        elegidas.append(mejor[0])
        pasos.append({"paso": len(elegidas), "entra": mejor[0], "p_razon_verosimilitud": mejor[2],
                      "log_verosimilitud": mejor[1], "vif_max": mejor[3]})
        ll_actual = mejor[1]
    return pd.DataFrame(pasos)


def score_band_table(scores: np.ndarray, y: pd.Series, edges) -> pd.DataFrame:
    """Default por banda de score (bandas fijas), con IC de Wilson. Score alto = menos riesgo."""
    from .eda import wilson_ci
    banda = pd.cut(pd.Series(scores), edges)
    d = pd.DataFrame({"banda": banda.astype(str).to_numpy(), "y": pd.Series(y).to_numpy()})
    orden = [str(c) for c in banda.cat.categories]
    t = d.groupby("banda")["y"].agg(creditos="size", defaults="sum").reindex(orden).dropna()
    t["pct_creditos"] = t["creditos"] / t["creditos"].sum()
    t["default_rate"] = t["defaults"] / t["creditos"]
    t["ic_inf"], t["ic_sup"] = wilson_ci(t["defaults"], t["creditos"])
    t.index.name = "banda_score"
    return t
