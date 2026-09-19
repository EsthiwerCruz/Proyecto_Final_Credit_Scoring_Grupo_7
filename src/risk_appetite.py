"""Risk Appetite (sección 6.1): umbrales, métricas de cartera, semáforo,
tipo de métrica, regla de precedencia y prueba de factibilidad.

Cada métrica tiene dirección ("min": debe ser >= umbral, "max": debe ser
<= umbral), un umbral verde y un umbral rojo; entre ambos es ámbar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg

RISK_APPETITE = [
    # dimension, key, metrica, direccion, verde, rojo, racional
    ("Crecimiento", "approval_rate_ttd", "Tasa de aprobación sobre solicitudes (TTD)", "min", 0.70, 0.65,
     "Mandato de crecer fuera de agencias; no caer >13 pp vs. histórico (82.6%)."),
    ("Riesgo", "default_rate_12m", "Default 12m (90+ DPD) de cosechas aprobadas", "max", 0.11, 0.13,
     "Volver a la media histórica (11.6%); 2024-2025 estuvo en 13.4%-14.0%."),
    ("Riesgo", "el_rate", "Expected Loss / monto desembolsado (PD x EAD x LGD)", "max", 0.030, 0.035,
     "Pérdida realizada histórica 2.9%; 2024 llegó a 4.0%."),
    ("Riesgo", "lgd_mean", "LGD media de defaults", "max", 0.65, 0.70,
     "Crédito sin garantía: LGD histórica 62.3%, estable 61%-63%."),
    ("Concentración", "max_region_share", "Mayor participación de una macrorregión en el monto", "max", 0.45, 0.50,
     "Riesgo climático/zonal correlacionado; Lima concentra 41.6%."),
    ("Concentración", "alianza_share", "Participación del canal alianza en el monto", "max", 0.15, 0.20,
     "Riesgo de intermediario (datos inflados); hoy 9.6%."),
    ("Concentración", "new_customer_share", "Participación de clientes nuevos en el monto", "max", 0.50, 0.55,
     "Clientes sin relación: default 12.7% vs 10.7%; hoy 44.8%."),
    ("Concentración", "thin_file_share", "Participación de clientes sin score de buró en el monto", "max", 0.05, 0.08,
     "Score no disponible (su historial de buró existe): exposición acotada mientras se re-consulta; hoy 3.2%."),
    ("Concentración", "long_term_share", "Participación de plazos > 36 meses en el monto", "max", 0.25, 0.30,
     "Plazos largos exceden la ventana de 12m y el ciclo productivo; hoy 24.1%."),
    ("Concentración", "large_ticket_share", "Participación de montos > S/ 20,000 en el monto", "max", 0.12, 0.15,
     "Tickets fuera del rango de microcrédito; 4.2% de operaciones pero 14.5% del monto."),
    ("Concentración", "remote_share", "Participación de clientes a > 50 km de agencia en el monto", "max", 0.03, 0.05,
     "Costo de servir/cobrar; hoy 1.7%."),
    ("Capacidad de pago", "dti_post_gt60_share", "Monto aprobado con DTI post-crédito > 60%", "max", 0.05, 0.10,
     "Sobreendeudamiento: default 16.8% con DTI post 60%-80%; hoy 21.6% del monto (sin control)."),
    ("Fair lending", "air_region", "Adverse Impact Ratio de aprobación entre macrorregiones", "min", 0.90, 0.80,
     "Regla 4/5; Oriente tiene la menor aprobación (78.8%) con el menor default."),
    ("Fair lending", "air_cash", "Adverse Impact Ratio de aprobación entre quintiles de ingreso en efectivo", "min", 0.90, 0.80,
     "No excluir por falta de trazabilidad bancaria (objetivo del caso)."),
]

APPETITE_COLUMNS = ["dimension", "key", "metrica", "direccion", "verde", "rojo", "racional"]


# Naturaleza de cada métrica. Un límite de riesgo obliga a actuar; un objetivo de negocio orienta.
METRIC_TYPE = {
    "approval_rate_ttd": "Objetivo de negocio",
    "default_rate_12m": "Límite de riesgo", "el_rate": "Límite de riesgo", "lgd_mean": "Límite de riesgo",
    "dti_post_gt60_share": "Límite de riesgo",
    "max_region_share": "Límite de concentración", "alianza_share": "Límite de concentración",
    "new_customer_share": "Límite de concentración", "thin_file_share": "Límite de concentración",
    "long_term_share": "Límite de concentración", "large_ticket_share": "Límite de concentración",
    "remote_share": "Límite de concentración",
    "air_region": "Control de fair lending", "air_cash": "Control de fair lending",
}

PRECEDENCE_RULE = (
    "Si el objetivo de aprobación choca con un límite de riesgo, prevalece el límite: no se relaja el "
    "punto de corte para sostener la aprobación. Una aprobación en Ámbar o Rojo se escala al Comité, que "
    "decide acciones comerciales (canales, montos, pricing) o una revisión formal del apetito. Los controles "
    "de fair lending no se compensan con otras métricas: un AIR en Rojo exige revisar la política aunque el "
    "resto esté en Verde."
)


def appetite_table() -> pd.DataFrame:
    tab = pd.DataFrame(RISK_APPETITE, columns=APPETITE_COLUMNS)
    tab.insert(2, "tipo", tab["key"].map(METRIC_TYPE))
    return tab


def traffic_light(value: float, direction: str, green: float, red: float) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/D"
    if direction == "min":
        return "Verde" if value >= green else ("Ámbar" if value >= red else "Rojo")
    return "Verde" if value <= green else ("Ámbar" if value <= red else "Rojo")


def monthly_installment(amount, term_months, annual_rate=cfg.REFERENCE_ANNUAL_RATE):
    """Cuota de amortización francesa con tasa efectiva anual (TEA) convertida a mensual."""
    amount = np.asarray(amount, dtype="float64")
    n = np.asarray(term_months, dtype="float64")
    r = (1 + np.asarray(annual_rate, dtype="float64")) ** (1 / 12) - 1
    return amount * r / (1 - (1 + r) ** (-n))


def dti_post(df: pd.DataFrame, annual_rate=cfg.REFERENCE_ANNUAL_RATE) -> pd.Series:
    """(Deuda mensual existente + cuota estimada del nuevo crédito) / ingreso mensual."""
    inst = monthly_installment(df["requested_amount"], df["term_months"], annual_rate)
    return (df["monthly_debt_payment"] + inst) / df["monthly_income"]


def _air(approved: pd.Series, groups: pd.Series) -> float:
    rates = approved.groupby(groups, observed=True).mean()
    return float(rates.min() / rates.max())


def portfolio_metrics(apps: pd.DataFrame, approved: pd.Series | None = None) -> dict:
    """Métricas del apetito sobre un conjunto de solicitudes (TTD).

    approved: máscara de aprobación (por defecto, approved_flag histórico).
    La Expected Loss se aproxima con la pérdida realizada EAD x LGD de los defaults.
    """
    approved = apps[cfg.APPROVED_FLAG].eq(1) if approved is None else approved.astype(bool)
    book = apps[approved]
    amount = book["requested_amount"]
    w = amount / amount.sum()
    perf = book[book[cfg.OUTCOME_FILTER].eq(1)]
    loss = (perf["ead_at_default"].fillna(0) * perf["lgd_observed"].fillna(0)).sum()
    region_share = amount.groupby(book["region"]).sum() / amount.sum()
    return {
        "approval_rate_ttd": float(approved.mean()),
        "default_rate_12m": float(perf[cfg.TARGET].mean()),
        "el_rate": float(loss / perf["requested_amount"].sum()),
        "lgd_mean": float(perf.loc[perf[cfg.TARGET].eq(1), "lgd_observed"].mean()),
        "max_region_share": float(region_share.max()),
        "alianza_share": float(w[book["channel"].eq("alianza")].sum()),
        "new_customer_share": float(w[book["new_customer_flag"].eq(1)].sum()),
        "thin_file_share": float(w[book["bureau_score"].isna()].sum()),
        "long_term_share": float(w[book["term_months"].gt(cfg.LONG_TERM_MONTHS)].sum()),
        "large_ticket_share": float(w[book["requested_amount"].gt(cfg.MICRO_MAX_AUTO_AMOUNT)].sum()),
        "remote_share": float(w[book["distance_to_branch_km"].gt(cfg.REMOTE_DISTANCE_KM)].sum()),
        "dti_post_gt60_share": float(w[dti_post(book).gt(cfg.DTI_POST_HARD_MAX)].sum()),
        "air_region": _air(approved, apps["region"]),
        "air_cash": _air(approved, pd.qcut(apps["cash_income_share"], 5)),
    }


def evaluate_appetite(metrics: dict) -> pd.DataFrame:
    """Cruza métricas observadas con el apetito y asigna semáforo."""
    tab = appetite_table()
    tab["valor"] = tab.key.map(metrics)
    tab["semaforo"] = [traffic_light(v, d, g, r) for v, d, g, r in zip(tab.valor, tab.direccion, tab.verde, tab.rojo)]
    return tab


def appetite_feasibility(apps: pd.DataFrame, years: list[int], approval_grid=(0.65, 0.70, 0.75, 0.80),
                         dr_limit: float = 0.11, el_limit: float = 0.030, n_bins: int = 10) -> pd.DataFrame:
    """¿Pueden cumplirse a la vez el objetivo de aprobación y los límites de default y EL?

    Para cada año se ordena TODA la población de solicitudes (TTD) por `bureau_score`
    (faltante = mediana del año) y se simula aprobar el X% de mejor score. Los aprobados
    históricos aportan su default y pérdida observados; a los rechazados que entran se les
    imputa el default y la pérdida de los aprobados de su mismo decil de score y año
    (parceling). Supuestos: el rechazado se comporta como el aprobado de igual score, y el
    orden se hace solo con buró, así que el modelo final debería ordenar igual o mejor.
    Por diseño se usan años de DEV y VAL; la cosecha OOT queda reservada.
    """
    rows = []
    for year in years:
        ttd = apps[apps[cfg.DATE_COL].dt.year == year].copy()
        ttd["_score"] = ttd["bureau_score"].fillna(ttd["bureau_score"].median())
        ttd["_bin"] = pd.qcut(ttd["_score"].rank(method="first"), n_bins, labels=False)
        aprobados = ttd[ttd[cfg.APPROVED_FLAG].eq(1)]
        perdida = aprobados["ead_at_default"].fillna(0) * aprobados["lgd_observed"].fillna(0)
        dr_bin = aprobados.groupby("_bin")[cfg.TARGET].mean()
        loss_bin = perdida.groupby(aprobados["_bin"]).sum() / aprobados.groupby("_bin")["requested_amount"].sum()
        es_aprobado = ttd[cfg.APPROVED_FLAG].eq(1)
        ttd["_default"] = np.where(es_aprobado, ttd[cfg.TARGET], ttd["_bin"].map(dr_bin))
        ttd["_perdida"] = np.where(es_aprobado, ttd["ead_at_default"].fillna(0) * ttd["lgd_observed"].fillna(0),
                                   ttd["_bin"].map(loss_bin) * ttd["requested_amount"])
        ttd = ttd.sort_values("_score", ascending=False).reset_index(drop=True)
        n = len(ttd)
        row = {"anio": year, "aprobacion_historica": float(es_aprobado.mean()),
               "default_historico": float(aprobados[cfg.TARGET].mean())}
        for a in approval_grid:
            s = ttd.iloc[: int(round(a * n))]
            row[f"default_aprob_{a:.0%}"] = float(s["_default"].mean())
            row[f"el_aprob_{a:.0%}"] = float(s["_perdida"].sum() / s["requested_amount"].sum())
        dr_acum = ttd["_default"].expanding().mean().to_numpy()
        el_acum = (ttd["_perdida"].cumsum() / ttd["requested_amount"].cumsum()).to_numpy()
        ok_dr, ok_el = np.where(dr_acum <= dr_limit)[0], np.where(el_acum <= el_limit)[0]
        row["aprobacion_max_default_ok"] = float((ok_dr.max() + 1) / n) if len(ok_dr) else 0.0
        row["aprobacion_max_el_ok"] = float((ok_el.max() + 1) / n) if len(ok_el) else 0.0
        row["aprobacion_max_ambos_ok"] = min(row["aprobacion_max_default_ok"], row["aprobacion_max_el_ok"])
        rows.append(row)
    return pd.DataFrame(rows).set_index("anio")
