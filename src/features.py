"""Variables derivadas y su pre-selección (sección 6.3).

Dos niveles:

* `build_features` construye lo que usa el pipeline en desarrollo y en
  producción: el `dti` recalculado desde sus insumos, las derivadas conservadas
  y los indicadores de faltante que usan la política y el monitoreo.
* `build_candidate_pool` agrega todas las derivadas que se evaluaron (también
  las descartadas) para reproducir la evidencia de la pre-selección, que decide
  `screen_derived_features` usando solo DEV.

Todo se calcula con información disponible en T0 y sin estadísticos de la
muestra. La cuota del crédito usa la TEA de referencia del producto
(`cfg.REFERENCE_ANNUAL_RATE`), no `annual_interest_rate_offer`, que es endógena.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg
from . import validation
from .risk_appetite import monthly_installment

# Tope para ratios con denominador pequeño (solo en la derivada descartada que lo usaba).
DTI_VERIFICABLE_CAP = 10.0

# -----------------------------------------------------------------------------
# Derivadas que construye el pipeline.
# feature, fórmula, racional, signo esperado, uso, ¿candidata al modelo PD?
# -----------------------------------------------------------------------------
FEATURE_DOC = [
    ("cuota_estimada",
     "monto * r / (1 - (1+r)^-plazo), con r = (1+TEA_ref)^(1/12) - 1",
     "Cuota mensual del crédito solicitado; insumo de la capacidad de pago.",
     "-", "Insumo (no predictor)", False),
    ("dti_post",
     "(monthly_debt_payment + cuota_estimada) / monthly_income",
     "Carga total de deuda si se aprueba el crédito. Como predictor es intercambiable con `dti` "
     "(miden lo mismo y ninguna aporta de forma robusta sobre la otra); se prefiere porque incorpora "
     "la cuota del crédito que se decide, así la PD reacciona a una contraoferta de monto o plazo, y es "
     "la misma medida de la regla de capacidad de pago.",
     "+", "Candidata PD (6.5 elige entre dti y dti_post) y regla de política", True),
    ("ahorro_sobre_monto",
     "savings_balance / requested_amount",
     "Colchón de ahorro frente al tamaño del crédito pedido. Es la derivada de ahorro que se conserva: "
     "`colchon_ahorro_meses` mide lo mismo y no agrega información.",
     "-", "Candidata PD (6.5 elige entre ella y savings_balance)", True),
    ("flag_sin_buro",
     "1 si bureau_score es nulo",
     "Score de buró no disponible. No identifica un cliente thin-file: estas solicitudes tienen el mismo "
     "historial de buró que el resto. Su menor default en DEV se concentra en 2021-2022 y desaparece en "
     "2023, por eso no entra al modelo; sirve para política (re-consultar el buró) y monitoreo.",
     "?", "Política y monitoreo (no predictor)", False),
    ("flag_sin_ingreso",
     "1 si monthly_income es nulo",
     "Sin ingreso no hay capacidad de pago calculable (dti y dti_post quedan faltantes). El faltante es "
     "compatible con MCAR y no predice default; en política deriva a verificación de ingreso.",
     "?", "Política y monitoreo (no predictor)", False),
    ("flag_sin_ahorro",
     "1 si savings_balance es nulo",
     "Faltante compatible con MCAR: igual en clientes nuevos y antiguos y sin relación con el default. "
     "Solo se monitorea su tasa como control de calidad de datos.",
     "?", "Monitoreo (no predictor)", False),
]
FEATURE_DOC_COLUMNS = ["feature", "formula", "racional", "signo_esperado", "uso", "candidata_pd"]

DERIVED_FEATURES = [f[0] for f in FEATURE_DOC]
DERIVED_CANDIDATES = [f[0] for f in FEATURE_DOC if f[5]]
DERIVED_INPUTS = [f[0] for f in FEATURE_DOC if f[4].startswith("Insumo")]
POLICY_FLAGS = ["flag_sin_buro", "flag_sin_ingreso", "flag_sin_ahorro"]

# -----------------------------------------------------------------------------
# Pool evaluado en la pre-selección (conservadas y descartadas).
# componentes: variables con las que se construye (R3 mide si la derivada agrega algo sobre ellas).
# sin_sensible: versión de la misma medida sin el componente sensible (R4).
# -----------------------------------------------------------------------------
SCREENING_SPEC = {
    "dti_post": dict(
        formula="(monthly_debt_payment + cuota_estimada) / monthly_income", signo="+",
        componentes=["dti", "requested_amount", "term_months"], sin_sensible=None),
    "ahorro_sobre_monto": dict(
        formula="savings_balance / requested_amount", signo="-",
        componentes=["savings_balance", "requested_amount"], sin_sensible=None),
    "colchon_ahorro_meses": dict(
        formula="savings_balance / cuota_estimada", signo="-",
        componentes=["savings_balance", "requested_amount", "term_months"], sin_sensible=None),
    "deuda_por_obligacion": dict(
        formula="monthly_debt_payment / (1 + active_loans)", signo="+",
        componentes=["monthly_debt_payment", "active_loans"], sin_sensible=None),
    "dti_post_verificable": dict(
        formula="(monthly_debt_payment + cuota_estimada) / (monthly_income * (1 - cash_income_share)), tope 10",
        signo="+", componentes=["dti_post", "cash_income_share"], sin_sensible="dti_post"),
    "excedente_per_capita": dict(
        formula="(monthly_income - monthly_debt_payment - cuota_estimada) / (1 + household_dependents)",
        signo="-", componentes=["monthly_income", "monthly_debt_payment", "requested_amount", "term_months",
                                "household_dependents"], sin_sensible="excedente_total"),
    "antiguedad_relativa": dict(
        formula="employment_tenure_months / ((age - 14) * 12), tope 1", signo="-",
        componentes=["employment_tenure_months", "age"], sin_sensible="employment_tenure_months"),
    "intensidad_busqueda": dict(
        formula="bureau_inquiries_6m / (1 + active_loans)", signo="+",
        componentes=["bureau_inquiries_6m", "active_loans"], sin_sensible=None),
    "campana_siembra": dict(
        formula="1 si el mes de observation_date está entre setiembre y diciembre", signo="+",
        componentes=[], sin_sensible=None),
    "loan_to_income": dict(
        formula="requested_amount / monthly_income", signo="+",
        componentes=["requested_amount", "monthly_income"], sin_sensible=None),
}

RULES = {
    "R1": "Señal en DEV con el signo esperado (Mann-Whitney, p < {a})",
    "R2": "Mantiene el signo esperado en 2021-2022 y en 2023 (no se invierte dentro de DEV)",
    "R3": "Aporta sobre el núcleo y sus propios componentes (test de razón de verosimilitud, p < {a})",
    "R4": "Si usa una variable sensible, esta aporta sobre la versión sin ella (p < {a})",
    "R5": "No es redundante con otra derivada que pasa R1-R4 (Spearman > {rho}); se queda la de más señal",
}
_RULE_FAIL_TEXT = {
    "R1": "sin señal en DEV o con signo contrario al esperado",
    "R2": "no mantiene el signo esperado en 2021-2022 y en 2023",
    "R3": "no agrega información sobre sus propios componentes",
    "R4": "el componente sensible no pasa la prueba de necesidad de negocio",
    "R5": "redundante con otra derivada conservada",
}

# Descartadas antes de esta revisión cuya evidencia no se recalcula aquí.
DISCARDED_PRIOR = [
    ("monto_vs_mediana_region", "requested_amount / mediana del monto en la región (ajustada en DEV)",
     "AUC 0.501 en DEV; además introduce un estadístico de muestra que habría que versionar, sin ganancia."),
    ("mes_originacion", "mes calendario de observation_date",
     "Sin estacionalidad: el default no difiere por mes de originación (ver quality.seasonality_test)."),
]


def feature_doc() -> pd.DataFrame:
    return pd.DataFrame(FEATURE_DOC, columns=FEATURE_DOC_COLUMNS)


def build_features(df: pd.DataFrame, annual_rate: float = cfg.REFERENCE_ANNUAL_RATE) -> pd.DataFrame:
    """Variables que usa el pipeline. No modifica el DataFrame original.

    Regla de consistencia: `dti` se recalcula como monthly_debt_payment / monthly_income.
    En el archivo coincide con su fórmula, pero viene informado incluso cuando falta el
    ingreso, algo imposible en producción (sin ingreso no hay dti). Recalcularlo evita
    entrenar con información que el servicio de scoring no tendría.
    """
    x = df.copy()
    cuota = pd.Series(monthly_installment(x["requested_amount"], x["term_months"], annual_rate), index=x.index)
    x["dti"] = x["monthly_debt_payment"] / x["monthly_income"]
    x["cuota_estimada"] = cuota
    x["dti_post"] = (x["monthly_debt_payment"] + cuota) / x["monthly_income"]
    x["ahorro_sobre_monto"] = x["savings_balance"] / x["requested_amount"]
    x["flag_sin_buro"] = x["bureau_score"].isna().astype(int)
    x["flag_sin_ingreso"] = x["monthly_income"].isna().astype(int)
    x["flag_sin_ahorro"] = x["savings_balance"].isna().astype(int)
    return x.replace([np.inf, -np.inf], np.nan)


def build_candidate_pool(df: pd.DataFrame, annual_rate: float = cfg.REFERENCE_ANNUAL_RATE) -> pd.DataFrame:
    """`build_features` + todas las derivadas evaluadas en la pre-selección (evidencia)."""
    x = build_features(df, annual_rate)
    deuda_total = x["monthly_debt_payment"] + x["cuota_estimada"]
    x["ingreso_verificable"] = x["monthly_income"] * (1 - x["cash_income_share"])
    x["dti_post_verificable"] = (deuda_total / x["ingreso_verificable"]).clip(upper=DTI_VERIFICABLE_CAP)
    x["excedente_total"] = x["monthly_income"] - deuda_total
    x["excedente_per_capita"] = x["excedente_total"] / (1 + x["household_dependents"])
    x["colchon_ahorro_meses"] = x["savings_balance"] / x["cuota_estimada"]
    x["deuda_por_obligacion"] = x["monthly_debt_payment"] / (1 + x["active_loans"])
    x["intensidad_busqueda"] = x["bureau_inquiries_6m"] / (1 + x["active_loans"])
    x["antiguedad_relativa"] = (x["employment_tenure_months"] / ((x["age"] - 14) * 12)).clip(upper=1)
    x["campana_siembra"] = x[cfg.DATE_COL].dt.month.isin([9, 10, 11, 12]).astype(int)
    x["loan_to_income"] = x["requested_amount"] / x["monthly_income"]
    return x.replace([np.inf, -np.inf], np.nan)


def screen_derived_features(dev: pd.DataFrame, spec: dict = SCREENING_SPEC) -> pd.DataFrame:
    """Aplica las reglas R1-R5 usando SOLO la muestra DEV y devuelve la decisión por variable.

    `dev` debe venir de `build_candidate_pool`. Si trae la columna `sample`, se exige que
    todas las filas sean DEV: la pre-selección no puede mirar VAL ni OOT.
    """
    if "sample" in dev.columns and not dev["sample"].eq("DEV").all():
        raise ValueError("La pre-selección de variables se decide solo con DEV.")
    t = cfg.TARGET
    core = list(cfg.SCREEN_CORE)
    sub = {k: dev[dev[cfg.DATE_COL].between(pd.Timestamp(a), pd.Timestamp(b))]
           for k, (a, b) in cfg.DEV_SUBPERIODS.items()}
    rows = []
    for f, s in spec.items():
        auc, p = validation.auc_test(dev[t], dev[f])
        aucs_sub = {k: validation.auc_raw(d[t], d[f]) for k, d in sub.items()}
        p_comp = validation.lr_test(dev, t, core + [c for c in s["componentes"] if c != f], [f])
        p_sens = (validation.lr_test(dev, t, core + [s["sin_sensible"]], [f]) if s["sin_sensible"] else np.nan)
        r1 = validation.direction(auc) == s["signo"] and p < cfg.SCREEN_ALPHA_SIGNAL
        r2 = all(validation.direction(a) == s["signo"] for a in aucs_sub.values())
        r3 = p_comp < cfg.SCREEN_ALPHA_INCREMENTAL
        r4 = True if not s["sin_sensible"] else bool(p_sens < cfg.SCREEN_ALPHA_FAIRNESS)
        row = {"feature": f, "formula": s["formula"], "signo_esperado": s["signo"],
               "auc_dev": auc, "p_dev": p}
        row.update({f"auc_{k.lower()}": v for k, v in aucs_sub.items()})
        row.update({"p_aporte_sobre_componentes": p_comp, "p_necesidad_sensible": p_sens,
                    "R1": r1, "R2": r2, "R3": r3, "R4": r4})
        rows.append(row)
    out = pd.DataFrame(rows)

    # R5: redundancia entre las que pasan R1-R4; se conserva la de mayor |AUC - 0.5| en DEV.
    out["R5"] = True
    out["redundante_con"] = ""
    ok = out[out[["R1", "R2", "R3", "R4"]].all(axis=1)].copy()
    ok["fuerza"] = (ok["auc_dev"] - 0.5).abs()
    ok = ok.sort_values("fuerza", ascending=False)
    kept: list[str] = []
    for f in ok["feature"]:
        rho = {k: abs(dev[[f, k]].corr(method="spearman").iloc[0, 1]) for k in kept}
        close = [k for k, v in rho.items() if v > cfg.SCREEN_REDUNDANCY_RHO]
        if close:
            out.loc[out.feature == f, "R5"] = False
            out.loc[out.feature == f, "redundante_con"] = close[0]
        else:
            kept.append(f)

    reglas = ["R1", "R2", "R3", "R4", "R5"]
    out["decision"] = np.where(out[reglas].all(axis=1), "Conservada", "Descartada")
    out["motivo"] = [
        "Pasa R1-R5" if d == "Conservada" else
        "; ".join(f"{r}: {_RULE_FAIL_TEXT[r]}" + (f" ({rc})" if r == "R5" and rc else "")
                  for r in reglas if not row[r])
        for d, rc, (_, row) in zip(out["decision"], out["redundante_con"], out.iterrows())
    ]
    return out


def rules_doc() -> pd.DataFrame:
    textos = {
        "R1": RULES["R1"].format(a=cfg.SCREEN_ALPHA_SIGNAL),
        "R2": RULES["R2"],
        "R3": RULES["R3"].format(a=cfg.SCREEN_ALPHA_INCREMENTAL),
        "R4": RULES["R4"].format(a=cfg.SCREEN_ALPHA_FAIRNESS),
        "R5": RULES["R5"].format(rho=cfg.SCREEN_REDUNDANCY_RHO),
    }
    return pd.DataFrame({"regla": list(textos), "criterio": list(textos.values())})


def discarded_doc(screening: pd.DataFrame) -> pd.DataFrame:
    """Derivadas descartadas: las de la pre-selección (con su motivo) y las previas."""
    now = screening.loc[screening.decision.eq("Descartada"), ["feature", "formula", "motivo"]]
    now = now.rename(columns={"motivo": "motivo_descarte"})
    prior = pd.DataFrame(DISCARDED_PRIOR, columns=["feature", "formula", "motivo_descarte"])
    return pd.concat([now, prior], ignore_index=True)
