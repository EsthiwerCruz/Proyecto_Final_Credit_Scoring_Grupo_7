"""Motor de decisión, cut-off, pricing y rentabilidad (sección 6.9).

La decisión no es solo el score: combina PD **calibrada**, capacidad de pago, reglas
duras de política y el apetito de riesgo, y devuelve tres salidas (APPROVE, REVIEW,
REJECT) con su motivo, el monto recomendado y la tasa recomendada.

Economía (supuestos en `config.py`, discutidos en el reporte):

    margen        = monto x (tasa - costo de fondos - gasto operativo) x factor de saldo x plazo/12
    pérdida esperada = PD x EAD/monto x LGD x monto
    resultado     = margen - pérdida esperada

El EAD y la LGD usan por ahora los promedios observados en 6.4 (0.42 y 0.62); 6.10 y
6.11 los reemplazan por modelos y esta capa no cambia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as cfg
from .risk_appetite import monthly_installment

APPROVE, REVIEW, REJECT = "APPROVE", "REVIEW", "REJECT"


@dataclass
class DecisionPolicy:
    """Política de decisión. Los umbrales de PD se eligen con la curva de trade-off (§ del notebook)."""
    pd_approve_max: float = cfg.PD_APPROVE_MAX
    pd_reject_min: float = cfg.PD_REJECT_MIN
    dti_auto_max: float = cfg.DTI_POST_AUTO_MAX
    dti_hard_max: float = cfg.DTI_POST_HARD_MAX
    amount_auto_max: float = cfg.MICRO_MAX_AUTO_AMOUNT
    cash_share_review: float = cfg.HIGH_CASH_SHARE
    amount_cash_review: float = cfg.MANUAL_REVIEW_AMOUNT
    reference_rate: float = cfg.REFERENCE_ANNUAL_RATE
    meta: dict = field(default_factory=dict)

    # ---------- capacidad de pago ----------
    def max_amount_by_capacity(self, df: pd.DataFrame, dti_max: float | None = None) -> np.ndarray:
        """Monto máximo que deja el DTI post-crédito en el tope indicado.

        Por defecto usa el tope de aprobación automática (45%). Con `dti_max` se puede pedir
        el tope duro (60%), que es el techo que la política de 6.1 permite solo con ajuste de
        monto o plazo y validación del analista.
        """
        tope = self.dti_auto_max if dti_max is None else dti_max
        r = (1 + self.reference_rate) ** (1 / 12) - 1
        n = df["term_months"].to_numpy(dtype=float)
        anualidad = (1 - (1 + r) ** -n) / r                      # monto = cuota x anualidad
        cuota_disponible = tope * df["monthly_income"].to_numpy(dtype=float) - \
            df["monthly_debt_payment"].to_numpy(dtype=float)
        return np.maximum(0.0, cuota_disponible * anualidad)

    def recommended_amount(self, df: pd.DataFrame) -> np.ndarray:
        """Monto recomendado: el solicitado, acotado por capacidad de pago y por el tope del producto."""
        pedido = df["requested_amount"].to_numpy(dtype=float)
        por_capacidad = self.max_amount_by_capacity(df)
        sin_ingreso = df["monthly_income"].isna().to_numpy()
        tope = np.where(sin_ingreso, pedido, np.floor(np.maximum(por_capacidad, 0) / 100) * 100)
        return np.minimum(pedido, tope)                           # contraoferta redondeada a S/ 100

    # ---------- pricing por riesgo ----------
    def risk_based_rate(self, pd_hat: np.ndarray, df: pd.DataFrame) -> np.ndarray:
        """Tasa = fondeo + gasto operativo + prima de riesgo + margen objetivo, con piso y techo.

        La prima de riesgo convierte la pérdida esperada sobre el monto en una tasa anual
        equivalente sobre el saldo promedio, que es lo que efectivamente se cobra.
        """
        plazo_anios = np.maximum(df["term_months"].to_numpy(dtype=float) / 12, 1e-6)
        el_sobre_monto = np.asarray(pd_hat, dtype=float) * cfg.EAD_FACTOR_BASELINE * cfg.LGD_BASELINE
        prima = el_sobre_monto / (cfg.AVG_BALANCE_FACTOR * plazo_anios)
        tasa = cfg.COST_OF_FUNDS + cfg.OPERATING_COST_RATE + prima + cfg.TARGET_MARGIN
        return np.clip(tasa, cfg.RATE_FLOOR, cfg.RATE_CAP)

    # ---------- decisión ----------
    def decide(self, df: pd.DataFrame, pd_hat: np.ndarray, recalcular_pd=None) -> pd.DataFrame:
        """Aplica el árbol de decisión y devuelve decisión, motivo, monto y tasa recomendados.

        Orden: rechazo por riesgo, reglas duras que siempre van a analista, contraoferta
        automática de monto por capacidad de pago y, recién al final, la zona gris de PD.
        Exceder el DTI **no** manda a revisión: dispara una contraoferta, y solo pasa a
        analista si el monto que resiste la capacidad de pago deja de ser comercial.

        `recalcular_pd` (opcional) recibe el DataFrame con el monto contraofertado y
        devuelve la PD recalculada: el scorecard reacciona al monto a través del DTI
        post-crédito, así que una contraoferta baja la PD de verdad.
        """
        pd_hat = np.asarray(pd_hat, dtype=float)
        n = len(df)
        decision = np.full(n, APPROVE, dtype=object)
        motivo = np.full(n, "Riesgo y capacidad dentro del apetito", dtype=object)

        monto_solicitado = df["requested_amount"].to_numpy(dtype=float)
        monto = self.recommended_amount(df)
        contraoferta = monto < 0.99 * monto_solicitado            # solo reducciones materiales

        # La PD se recalcula con el monto que realmente se ofrecería.
        if recalcular_pd is not None and contraoferta.any():
            ajustado = df.copy()
            ajustado["requested_amount"] = monto
            pd_hat = np.where(contraoferta, np.asarray(recalcular_pd(ajustado), dtype=float), pd_hat)

        sin_buro = df["bureau_score"].isna().to_numpy()
        sin_ingreso = df["monthly_income"].isna().to_numpy()
        efectivo_alto = (df["cash_income_share"].to_numpy(dtype=float) > self.cash_share_review) & \
            (monto_solicitado > self.amount_cash_review)

        def marcar(mascara, valor, texto):
            nuevos = np.asarray(mascara) & (decision == APPROVE)
            decision[nuevos] = valor
            motivo[nuevos] = texto

        # 1) Falta de información: la PD no es confiable porque su insumo principal está imputado.
        #    Estas reglas van ANTES del rechazo: sin score o sin ingreso no se rechaza en automático,
        #    se verifica. Es lo que fija la política de 6.1 y lo que sostiene el análisis de fairness de 6.8.
        marcar(sin_buro, REVIEW, "Sin score de buró: re-consultar y verificar identidad")
        marcar(sin_ingreso, REVIEW, "Sin ingreso declarado: verificar capacidad de pago en campo")
        # 2) Riesgo fuera del apetito aun con contraoferta (aquí el modelo sí tiene toda su información).
        marcar(pd_hat >= self.pd_reject_min, REJECT, f"PD calibrada >= {self.pd_reject_min:.0%}")
        # 3) Verificación obligatoria cuando el dato existe pero hay que sustentarlo.
        marcar(monto_solicitado > self.amount_auto_max, REVIEW,
               f"Monto > S/ {self.amount_auto_max:,.0f}: revisión obligatoria")
        marcar(efectivo_alto, REVIEW, "Ingreso mayormente en efectivo con ticket alto: verificar ingreso")
        # 4) La capacidad de pago no alcanza ni para un monto comercial.
        #    Si además el riesgo está fuera del tramo automático, no hay producto viable: se rechaza.
        #    Si el cliente es de bajo riesgo, va a analista para evaluar plazo mayor o consolidación.
        sin_capacidad = monto < cfg.MIN_VIABLE_AMOUNT
        marcar(sin_capacidad & (pd_hat > self.pd_approve_max), REJECT,
               "Capacidad de pago insuficiente y PD fuera del tramo automático")
        marcar(sin_capacidad, REVIEW, "Capacidad de pago insuficiente: evaluar plazo mayor o consolidación")
        # 5) Zona gris de riesgo.
        marcar(pd_hat > self.pd_approve_max, REVIEW,
               f"PD calibrada entre {self.pd_approve_max:.0%} y {self.pd_reject_min:.0%}")
        # 6) Aprobados con contraoferta material de monto (más de 1% por debajo de lo pedido).
        marcar_contra = contraoferta & (decision == APPROVE)
        motivo[marcar_contra] = "Aprobado con contraoferta de monto por capacidad de pago"

        # A quien va a analista por capacidad se le calcula el techo del 60%, que es hasta donde
        # la política permite llegar con validación: el analista recibe un monto concreto, no un "no".
        monto_revision = np.minimum(monto_solicitado,
                                    np.floor(self.max_amount_by_capacity(df, self.dti_hard_max) / 100) * 100)
        usa_techo = (decision == REVIEW) & sin_capacidad & (monto_revision >= cfg.MIN_VIABLE_AMOUNT)
        monto = np.where(usa_techo, monto_revision, monto)

        out = pd.DataFrame({"decision": decision, "motivo": motivo, "pd_calibrada": pd_hat}, index=df.index)
        out["monto_recomendado"] = monto
        out["contraoferta"] = contraoferta
        out["tasa_recomendada"] = self.risk_based_rate(pd_hat, df)
        out.loc[out.decision == REJECT, ["monto_recomendado", "tasa_recomendada"]] = np.nan
        return out

    def final_approval(self, decisiones: pd.DataFrame, tasa_revision: float = cfg.REVIEW_APPROVAL_RATE) -> float:
        """Aprobación final esperada = automáticas + la fracción de revisiones que el analista aprueba."""
        auto = float((decisiones["decision"] == APPROVE).mean())
        return auto + tasa_revision * float((decisiones["decision"] == REVIEW).mean())

# ---------------------------------------------------------------------------
# Economía
# ---------------------------------------------------------------------------
def expected_loss(df: pd.DataFrame, pd_hat, monto=None) -> np.ndarray:
    monto = df["requested_amount"].to_numpy(dtype=float) if monto is None else np.asarray(monto, dtype=float)
    return np.asarray(pd_hat, dtype=float) * cfg.EAD_FACTOR_BASELINE * cfg.LGD_BASELINE * monto


def expected_margin(df: pd.DataFrame, tasa, monto=None) -> np.ndarray:
    monto = df["requested_amount"].to_numpy(dtype=float) if monto is None else np.asarray(monto, dtype=float)
    plazo_anios = df["term_months"].to_numpy(dtype=float) / 12
    spread = np.asarray(tasa, dtype=float) - cfg.COST_OF_FUNDS - cfg.OPERATING_COST_RATE
    return monto * spread * cfg.AVG_BALANCE_FACTOR * plazo_anios


def portfolio_result(df: pd.DataFrame, aprobados: np.ndarray, pd_hat, tasa, monto=None,
                     default_esperado=None) -> dict:
    """Resultado esperado de la cartera aprobada: aprobación, default, EL y margen.

    `default_esperado` permite usar el default observado donde existe y la PD donde no
    (solicitudes históricamente rechazadas), que es el supuesto de parceling de 6.1.
    """
    monto = df["requested_amount"].to_numpy(dtype=float) if monto is None else np.asarray(monto, dtype=float)
    pd_hat = np.asarray(pd_hat, dtype=float)
    y = pd_hat if default_esperado is None else np.asarray(default_esperado, dtype=float)
    m = np.asarray(aprobados, dtype=bool)
    if m.sum() == 0:
        return {"aprobacion": 0.0, "default_esperado": np.nan, "el_sobre_monto": np.nan,
                "margen_sobre_monto": np.nan, "resultado_sobre_monto": np.nan, "creditos": 0}
    monto_ap = monto[m]
    el = y[m] * cfg.EAD_FACTOR_BASELINE * cfg.LGD_BASELINE * monto_ap
    margen = expected_margin(df[m], np.asarray(tasa, dtype=float)[m], monto_ap)
    return {"aprobacion": float(m.mean()), "default_esperado": float(y[m].mean()),
            "el_sobre_monto": float(el.sum() / monto_ap.sum()),
            "margen_sobre_monto": float(margen.sum() / monto_ap.sum()),
            "resultado_sobre_monto": float((margen.sum() - el.sum()) / monto_ap.sum()),
            "creditos": int(m.sum())}


def tradeoff_curve(df: pd.DataFrame, pd_hat, politica: DecisionPolicy, grid=None,
                   default_esperado=None, incluir_reglas: bool = True) -> pd.DataFrame:
    """Curva de trade-off al mover el umbral de aprobación automática.

    Para cada umbral se recalcula la política completa (incluidas las reglas duras) y se
    reportan aprobación, revisión, default esperado, EL y resultado económico.
    """
    grid = np.round(np.arange(0.04, 0.31, 0.01), 3) if grid is None else grid
    filas = []
    for umbral in grid:
        p = DecisionPolicy(**{**politica.__dict__, "pd_approve_max": float(umbral),
                              "pd_reject_min": max(float(umbral), politica.pd_reject_min)})
        d = p.decide(df, pd_hat) if incluir_reglas else None
        if d is None:
            aprobados = np.asarray(pd_hat) <= umbral
            tasa = p.risk_based_rate(pd_hat, df)
            monto = df["requested_amount"].to_numpy(dtype=float)
        else:
            aprobados = (d["decision"] == APPROVE).to_numpy()
            tasa = d["tasa_recomendada"].fillna(0).to_numpy()
            monto = d["monto_recomendado"].fillna(0).to_numpy()
        res = portfolio_result(df, aprobados, pd_hat, tasa, monto=monto, default_esperado=default_esperado)
        res["pd_approve_max"] = float(umbral)
        if d is not None:
            res["revision"] = float((d["decision"] == REVIEW).mean())
            res["rechazo"] = float((d["decision"] == REJECT).mean())
            res["aprobacion_final_esperada"] = p.final_approval(d)
        filas.append(res)
    return pd.DataFrame(filas).set_index("pd_approve_max")


def policy_summary(df: pd.DataFrame, decisiones: pd.DataFrame, pd_hat, default_esperado=None) -> dict:
    """Resumen de una política ya aplicada: mezcla de decisiones, riesgo y economía."""
    aprobados = (decisiones["decision"] == APPROVE).to_numpy()
    res = portfolio_result(df, aprobados, pd_hat, decisiones["tasa_recomendada"].fillna(0).to_numpy(),
                           monto=decisiones["monto_recomendado"].fillna(0).to_numpy(),
                           default_esperado=default_esperado)
    revisados = (decisiones["decision"] == REVIEW).to_numpy()
    y = np.asarray(default_esperado if default_esperado is not None else pd_hat, dtype=float)
    monto_final = decisiones["monto_recomendado"].fillna(0).to_numpy()
    tasa_rev = cfg.REVIEW_APPROVAL_RATE
    peso = np.where(aprobados, 1.0, np.where(revisados, tasa_rev, 0.0))   # cartera final esperada
    if peso.sum() > 0:
        el_final = (y * cfg.EAD_FACTOR_BASELINE * cfg.LGD_BASELINE * monto_final * peso).sum()
        margen_final = (expected_margin(df, decisiones["tasa_recomendada"].fillna(0).to_numpy(), monto_final) * peso).sum()
        monto_pond = (monto_final * peso).sum()
        res.update({"aprobacion_final_esperada": float(peso.mean()),
                    "default_cartera_final": float((y * peso).sum() / peso.sum()),
                    "el_cartera_final": float(el_final / monto_pond),
                    "resultado_cartera_final": float((margen_final - el_final) / monto_pond)})
    res.update({"revision": float((decisiones["decision"] == REVIEW).mean()),
                "rechazo": float((decisiones["decision"] == REJECT).mean()),
                "tasa_media_recomendada": float(decisiones.loc[aprobados, "tasa_recomendada"].mean()),
                "monto_recomendado_sobre_solicitado": float(
                    decisiones.loc[aprobados, "monto_recomendado"].sum() / df.loc[aprobados, "requested_amount"].sum())})
    return res


def swap_analysis(df: pd.DataFrame, decisiones: pd.DataFrame, aprobado_historico: pd.Series,
                  target: str = cfg.TARGET) -> pd.DataFrame:
    """Swap-in / swap-out contra la política histórica, con el default observado donde existe."""
    d = pd.DataFrame({"nueva": decisiones["decision"].to_numpy(),
                      "historica": np.where(aprobado_historico.to_numpy() == 1, "Aprobado", "Rechazado"),
                      "y": df[target].to_numpy(), "monto": df["requested_amount"].to_numpy()})
    d["grupo"] = np.select(
        [(d.historica == "Aprobado") & (d.nueva == APPROVE), (d.historica == "Aprobado") & (d.nueva != APPROVE),
         (d.historica == "Rechazado") & (d.nueva == APPROVE), (d.historica == "Rechazado") & (d.nueva != APPROVE)],
        ["Se mantienen aprobados", "Swap-out: salen", "Swap-in: entran", "Se mantienen fuera"], default="Otro")
    t = d.groupby("grupo").agg(solicitudes=("y", "size"), monto=("monto", "sum"))
    observados = d[d.historica == "Aprobado"].groupby("grupo")["y"].agg(["size", "mean"])
    t["default_observado"] = observados["mean"]
    t["pct_solicitudes"] = t["solicitudes"] / t["solicitudes"].sum()
    return t
