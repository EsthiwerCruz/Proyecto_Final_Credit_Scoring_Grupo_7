"""Perfilado de calidad de datos (sección 6.3).

Cubre completitud, duplicidad, consistencia y lógica de negocio, rangos y
outliers, cardinalidad y estabilidad temporal. Las funciones devuelven tablas
para poder repetir el perfilado sobre cualquier extracción futura.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from . import config as cfg
from . import validation
from .risk_appetite import monthly_installment
from .validation import psi, psi_categorical, psi_label

# Salario mínimo de referencia usado solo como control de plausibilidad.
MIN_WAGE_REF = 1_025

# (regla, función que marca VIOLACIONES, severidad, tratamiento adoptado)
CONSISTENCY_RULES = [
    ("dti = cuota de deuda / ingreso (filas con ingreso)", lambda d: (d.monthly_debt_payment / d.monthly_income - d.dti).abs().gt(1e-3),
     "Alta", "Sin violaciones: el dti del archivo es coherente con sus insumos."),
    ("dti informado con ingreso faltante", lambda d: d.dti.notna() & d.monthly_income.isna(),
     "Media", "Imposible en producción (dti = cuota / ingreso). El pipeline recalcula dti desde sus insumos: "
              "sin ingreso queda faltante y se imputa, igual que lo haría el servicio de scoring."),
    ("new_customer_flag = 1 <-> relationship_months = 0", lambda d: d.new_customer_flag.eq(1) != d.relationship_months.eq(0),
     "Alta", "Sin violaciones."),
    ("antigüedad laboral <= (edad - 14) * 12", lambda d: d.employment_tenure_months.gt((d.age - 14) * 12),
     "Media", "Se conserva el registro; la winsorización p1-p99 limita el extremo y se reporta al equipo de captura."),
    ("relación con la Caja <= (edad - 18) * 12", lambda d: d.relationship_months.gt((d.age - 18) * 12),
     "Baja", "Se conserva: es plausible una cuenta de ahorros abierta antes de la mayoría de edad. Se marca para revisión de captura."),
    ("edad entre 18 y 75 años", lambda d: ~d.age.between(18, 75), "Bloqueante", "Sin violaciones."),
    ("edad + plazo <= 75 años al vencimiento", lambda d: (d.age + d.term_months / 12).gt(75),
     "Bloqueante", "Sin violaciones."),
    ("cash_income_share dentro de [0, 1]", lambda d: ~d.cash_income_share.between(0, 1), "Alta", "Sin violaciones."),
    ("dti <= 1", lambda d: d.dti.gt(1), "Alta", "Sin violaciones."),
    ("monto solicitado > 0", lambda d: d.requested_amount.le(0), "Bloqueante", "Sin violaciones."),
    ("plazo dentro del catálogo del producto", lambda d: ~d.term_months.isin([6, 9, 12, 18, 24, 36, 48, 60]),
     "Alta", "Sin violaciones."),
    ("bureau_score dentro de [300, 900]", lambda d: ~(d.bureau_score.between(300, 900) | d.bureau_score.isna()),
     "Alta", "Sin violaciones."),
    ("savings_balance >= 0", lambda d: d.savings_balance.lt(0), "Alta", "Sin violaciones."),
    ("default = 1 -> exposición informada", lambda d: d[cfg.TARGET].eq(1) & d.ead_at_default.isna(),
     "Alta", "Sin violaciones: los 671 defaults tienen EAD y LGD."),
    ("default = 0 -> campos post-default vacíos", lambda d: d[cfg.TARGET].eq(0) & d.ead_at_default.notna(),
     "Alta", "Sin violaciones: no hay contaminación de campos post-evento."),
    ("EAD <= monto solicitado", lambda d: d.ead_at_default.gt(d.requested_amount), "Media", "Sin violaciones."),
    ("recuperaciones <= EAD", lambda d: d.recovery_amount_total.gt(d.ead_at_default), "Media", "Sin violaciones."),
    ("cuota estimada <= ingreso mensual",
     lambda d: pd.Series(monthly_installment(d.requested_amount, d.term_months), index=d.index).gt(d.monthly_income),
     "Alta", "Caso aislado: la solicitud es inviable por capacidad y la regla de DTI la deriva a revisión."),
    (f"ingreso mensual >= S/ {MIN_WAGE_REF:,} (referencia)", lambda d: d.monthly_income.lt(MIN_WAGE_REF),
     "Informativa", "Se conservan: en el segmento rural informal un ingreso bajo la referencia es plausible, no un error."),
    ("distancia a agencia > 0", lambda d: d.distance_to_branch_km.le(0), "Alta", "Sin violaciones."),
]


def completeness(df: pd.DataFrame, cols: list[str], by: str | None = None) -> pd.DataFrame:
    """% de faltantes por variable, opcionalmente abierto por muestra o periodo."""
    total = df[cols].isna().mean().rename("total")
    if by is None:
        return total.to_frame().sort_values("total", ascending=False)
    parts = df.groupby(by)[cols].apply(lambda g: g.isna().mean()).T
    out = parts.join(total)
    return out.loc[out["total"].sort_values(ascending=False).index]


def duplicates_report(df: pd.DataFrame, business_key: list[str]) -> pd.DataFrame:
    """Duplicados por identificador, por fila completa y por clave de negocio."""
    rows = [
        ("Identificador duplicado (application_id)", int(df[cfg.ID_COL].duplicated().sum())),
        ("Fila idéntica en todas las columnas (sin ID)", int(df.drop(columns=cfg.ID_COL).duplicated().sum())),
        (f"Clave de negocio duplicada ({' + '.join(business_key)})", int(df.duplicated(subset=business_key).sum())),
    ]
    out = pd.DataFrame(rows, columns=["control", "registros"])
    out["pct"] = out.registros / len(df)
    return out


def consistency_rules(df: pd.DataFrame, rules=CONSISTENCY_RULES) -> pd.DataFrame:
    """Evalúa las reglas de consistencia y lógica de negocio."""
    rows = []
    for name, fn, severity, treatment in rules:
        flags = fn(df).fillna(False)
        rows.append({"regla": name, "severidad": severity, "violaciones": int(flags.sum()),
                     "pct": float(flags.mean()), "tratamiento": treatment})
    return pd.DataFrame(rows).sort_values(["violaciones", "severidad"], ascending=[False, True])


def outlier_report(df: pd.DataFrame, cols: list[str], k: float = 3.0,
                   lower_q: float = 0.01, upper_q: float = 0.99) -> pd.DataFrame:
    """Rangos, asimetría y outliers por regla de Tukey (k*IQR), con los topes propuestos."""
    rows = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        fuera = (s < q1 - k * iqr) | (s > q3 + k * iqr)
        rows.append({
            "variable": c, "min": s.min(), "p1": s.quantile(lower_q), "mediana": s.median(),
            "p99": s.quantile(upper_q), "max": s.max(), "asimetria": s.skew(),
            "outliers_iqr": int(fuera.sum()), "pct_outliers": float(fuera.mean()),
            "tope_inferior": s.quantile(lower_q), "tope_superior": s.quantile(upper_q),
        })
    return pd.DataFrame(rows).sort_values("pct_outliers", ascending=False)


def cardinality_report(df: pd.DataFrame, cols: list[str], rare_threshold: float = 0.05) -> pd.DataFrame:
    """Cardinalidad y categorías poco frecuentes (candidatas a agrupación)."""
    rows = []
    for c in cols:
        s = df[c]
        n_unique = int(s.nunique(dropna=False))
        rare = ""
        if s.dtype == object or n_unique <= 12:
            vc = s.value_counts(normalize=True, dropna=False)
            chicas = vc[vc < rare_threshold]
            rare = ", ".join(f"{i} ({p:.1%})" for i, p in chicas.items())
        rows.append({"variable": c, "tipo": str(s.dtype), "n_unicos": n_unique,
                     "pct_unicos": n_unique / len(df), "categorias_menores_al_umbral": rare})
    return pd.DataFrame(rows).sort_values("n_unicos")


def temporal_stability(pop: pd.DataFrame, cols: list[str], cat_cols: list[str],
                       sample_col: str = "sample") -> pd.DataFrame:
    """PSI de cada variable entre DEV y las muestras posteriores."""
    ref = pop[pop[sample_col] == cfg.SAMPLE_ORDER[0]]
    rows = []
    for c in cols:
        fn = psi_categorical if c in cat_cols else psi
        row = {"variable": c}
        for s in cfg.SAMPLE_ORDER[1:]:
            row[f"psi_{s.lower()}"] = fn(ref[c], pop.loc[pop[sample_col] == s, c])
        rows.append(row)
    out = pd.DataFrame(rows)
    out["semaforo"] = out[f"psi_{cfg.SAMPLE_ORDER[-1].lower()}"].map(psi_label)
    return out.sort_values(f"psi_{cfg.SAMPLE_ORDER[-1].lower()}", ascending=False)


def target_stability(pop: pd.DataFrame, freq: str = "Y") -> pd.DataFrame:
    """Tasa de default por periodo de originación (estabilidad del target)."""
    periodo = pop[cfg.DATE_COL].dt.to_period(freq)
    out = pop.groupby(periodo).agg(creditos=(cfg.TARGET, "size"), defaults=(cfg.TARGET, "sum"),
                                   default_rate=(cfg.TARGET, "mean"))
    out["var_vs_periodo_previo"] = out["default_rate"].pct_change()
    return out


# -----------------------------------------------------------------------------
# Estacionalidad del target
# -----------------------------------------------------------------------------
def seasonality_test(pop: pd.DataFrame, n_sim: int = 5000, seed: int = cfg.SEED) -> tuple[pd.DataFrame, dict]:
    """¿El default depende del mes de originación?

    Devuelve la tabla mensual y un resumen con: chi-cuadrado de independencia mes x default,
    comparación del rango observado entre meses contra el rango que produciría el azar con
    los mismos tamaños mensuales, y setiembre-diciembre vs. resto.
    """
    t = cfg.TARGET
    mes = pop[cfg.DATE_COL].dt.month
    tabla = pop.groupby(mes)[t].agg(creditos="size", defaults="sum", default_rate="mean")
    tabla.index.name = "mes"
    chi2, p_chi2, dof, _ = stats.chi2_contingency(pd.crosstab(mes, pop[t]))
    rng = np.random.default_rng(seed)
    n = tabla["creditos"].to_numpy()
    p0 = pop[t].mean()
    rangos = np.array([np.ptp(rng.binomial(n, p0) / n) for _ in range(n_sim)])
    rango_obs = float(np.ptp(tabla["default_rate"]))
    campana = mes.isin([9, 10, 11, 12])
    resumen = {
        "chi2": float(chi2), "gl": int(dof), "p_chi2": float(p_chi2),
        "rango_observado": rango_obs, "rango_azar_mediana": float(np.median(rangos)),
        "rango_azar_p95": float(np.quantile(rangos, 0.95)), "p_rango": float(np.mean(rangos >= rango_obs)),
        "dr_set_dic": float(pop.loc[campana, t].mean()), "dr_resto": float(pop.loc[~campana, t].mean()),
        "p_set_dic": float(stats.fisher_exact(pd.crosstab(campana, pop[t]).to_numpy())[1]),
        "mes_max": int(tabla["default_rate"].idxmax()),
    }
    return tabla, resumen


# -----------------------------------------------------------------------------
# Mecanismo de los faltantes
# -----------------------------------------------------------------------------
MISSING_VARS = ["monthly_income", "bureau_score", "savings_balance"]
# Variables que son función de la variable con faltantes y no deben explicar su ausencia.
_DERIVED_FROM = {"monthly_income": ["dti"]}


def _missing_design(df: pd.DataFrame, num_cols: list[str], cat_cols: list[str]) -> pd.DataFrame:
    z = validation._design(df, num_cols)
    return pd.concat([z, pd.get_dummies(df[cat_cols], drop_first=True).astype(float)], axis=1)


def missingness_report(raw: pd.DataFrame, pop: pd.DataFrame, candidates: list[str], cat_cols: list[str],
                       variables: list[str] = MISSING_VARS, seed: int = cfg.SEED) -> pd.DataFrame:
    """Diagnóstico del mecanismo de cada faltante y de su relación con el default.

    1. Estabilidad: ¿la tasa de faltante cambia por año o con la aprobación? (solicitudes TTD)
    2. MCAR vs. MAR: ¿se puede predecir el faltante con las demás variables de T0?
       Logit sobre TTD: test de razón de verosimilitud contra el modelo nulo y AUC con validación cruzada.
    3. ¿Es informativo del riesgo? Default con y sin faltante en DEV, controlado por el núcleo de
       riesgo, y por subperiodo de DEV. VAL se muestra solo como información.
    """
    t = cfg.TARGET
    dev = pop[pop["sample"] == "DEV"]
    val = pop[pop["sample"] == "VAL"]
    sub = {k: dev[dev[cfg.DATE_COL].between(pd.Timestamp(a), pd.Timestamp(b))]
           for k, (a, b) in cfg.DEV_SUBPERIODS.items()}
    rows = []
    for var in variables:
        excluir = {var, *_DERIVED_FROM.get(var, [])}
        nums = [c for c in candidates if c not in cat_cols and c not in excluir]
        m = raw[var].isna().astype(int)

        p_anio = stats.chi2_contingency(pd.crosstab(raw[cfg.DATE_COL].dt.year, m))[1]
        p_aprob = stats.fisher_exact(pd.crosstab(m, raw[cfg.APPROVED_FLAG]).to_numpy())[1]

        z = _missing_design(raw, nums, cat_cols)
        y = m.to_numpy()
        ll_full = validation._loglik(z, y)
        p0 = y.mean()
        ll_null = float(np.sum(y * np.log(p0) + (1 - y) * np.log(1 - p0)))
        p_modelo = stats.chi2.sf(2 * (ll_full - ll_null), z.shape[1])
        cv = StratifiedKFold(5, shuffle=True, random_state=seed)
        prob = cross_val_predict(LogisticRegression(max_iter=5000), z, y, cv=cv, method="predict_proba")[:, 1]
        auc_cv = roc_auc_score(y, prob)

        flag_dev = dev[var].isna()
        p_def = stats.fisher_exact(pd.crosstab(flag_dev, dev[t]).to_numpy())[1]
        base = [c for c in cfg.SCREEN_CORE if c not in excluir]
        d = dev.assign(_faltante=flag_dev.astype(float))
        p_ctrl = validation.lr_test(d, t, base, ["_faltante"])

        row = {
            "variable": var, "pct_faltante_ttd": float(m.mean()),
            "p_tasa_por_anio": float(p_anio), "p_relacion_aprobacion": float(p_aprob),
            "p_modelo_faltante": float(p_modelo), "auc_cv_modelo_faltante": float(auc_cv),
            "n_faltante_dev": int(flag_dev.sum()), "defaults_faltante_dev": int(dev.loc[flag_dev, t].sum()),
            "dr_faltante_dev": float(dev.loc[flag_dev, t].mean()), "dr_resto_dev": float(dev.loc[~flag_dev, t].mean()),
            "p_default_dev": float(p_def), "p_default_dev_controlado": float(p_ctrl),
        }
        for k, s_ in sub.items():
            f_ = s_[var].isna()
            row[f"dr_faltante_{k.lower()}"] = float(s_.loc[f_, t].mean())
            row[f"dr_resto_{k.lower()}"] = float(s_.loc[~f_, t].mean())
        fv = val[var].isna()
        row["dr_faltante_val_info"] = float(val.loc[fv, t].mean())
        row["dr_resto_val_info"] = float(val.loc[~fv, t].mean())

        mcar = p_modelo >= 0.05 and auc_cv < 0.55 and p_anio >= 0.05 and p_aprob >= 0.05
        signos = [np.sign(row[f"dr_faltante_{k.lower()}"] - row[f"dr_resto_{k.lower()}"]) for k in sub]
        diff_sub = [abs(row[f"dr_faltante_{k.lower()}"] - row[f"dr_resto_{k.lower()}"]) for k in sub]
        if p_ctrl >= 0.05:
            riesgo = "no informativo del riesgo"
        elif len(set(signos)) > 1 or min(diff_sub) < 0.01:
            riesgo = "diferencia de riesgo inestable dentro de DEV (no se usa como predictor)"
        else:
            riesgo = "informativo del riesgo"
        row["conclusion"] = ("Compatible con MCAR" if mcar else "Depende de variables observadas (MAR)") + "; " + riesgo
        rows.append(row)
    return pd.DataFrame(rows)


def bureau_history_check(raw: pd.DataFrame) -> pd.DataFrame:
    """¿Quien no tiene score de buró es realmente thin-file (sin historial)?

    Compara las variables que reporta el propio buró entre solicitudes con y sin score.
    Si fueran thin-file, tendrían menos deudas, moras y consultas registradas.
    """
    sin = raw["bureau_score"].isna()
    rows = []
    for c in ["active_loans", "prior_delinquencies_24m", "bureau_inquiries_6m", "monthly_debt_payment"]:
        rows.append({"variable_de_buro": c, "media_sin_score": float(raw.loc[sin, c].mean()),
                     "media_con_score": float(raw.loc[~sin, c].mean()),
                     "p_ks": float(stats.ks_2samp(raw.loc[sin, c], raw.loc[~sin, c]).pvalue)})
    rows.append({"variable_de_buro": "% con al menos 1 deuda activa", "media_sin_score": float((raw.loc[sin, "active_loans"] > 0).mean()),
                 "media_con_score": float((raw.loc[~sin, "active_loans"] > 0).mean()), "p_ks": np.nan})
    rows.append({"variable_de_buro": "% con mora previa en 24m", "media_sin_score": float((raw.loc[sin, "prior_delinquencies_24m"] > 0).mean()),
                 "media_con_score": float((raw.loc[~sin, "prior_delinquencies_24m"] > 0).mean()), "p_ks": np.nan})
    return pd.DataFrame(rows)
