"""Monitoreo del modelo y de la política (sección 6.15).

Tres monitoreos distintos que suelen confundirse en un mismo tablero:

* **Datos**: ¿llega la misma población y con la misma calidad? (PSI, faltantes, volumen)
* **Modelo**: ¿sigue ordenando y con el nivel correcto? (Gini, KS, observado/predicho)
* **Negocio**: ¿la política produce el resultado esperado? (aprobación, default, EL, revisión)

Cada indicador trae umbral Verde/Ámbar/Rojo y **una acción concreta**. Los umbrales no son
convenciones: salen de lo medido en 6.7, 6.9 y 6.12 (por ejemplo, el piso de Gini es el
límite inferior de la banda histórica entre cosechas, no un número redondo).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg
from . import evaluation as ev
from . import validation

# indicador, tipo, verde, ámbar, dirección ("max": peor cuando sube), acción ante ámbar, acción ante rojo, origen
INDICADORES = [
    ("PSI del score", "Datos", 0.10, 0.25, "max",
     "Investigar el cambio de mezcla y revisar canales", "Revisar el modelo: reentrenar si el cambio es estructural", "6.7"),
    ("PSI de una variable del scorecard", "Datos", 0.10, 0.25, "max",
     "Revisar la fuente de esa variable", "Reentrenar o reemplazar la variable", "6.7"),
    ("Tasa de faltantes de buró", "Datos", 0.05, 0.08, "max",
     "Revisar la consulta al buró antes de tocar el modelo", "Escalar al proveedor; limitar uso hasta normalizar", "6.3"),
    ("Volumen mensual de solicitudes", "Datos", 0.25, 0.40, "max",
     "Verificar cambios de campaña o de canal", "Validar que la mezcla no invalide la calibración", "6.4"),
    ("Gini de la cosecha", "Modelo", 0.35, 0.30, "min",
     "Investigar: puede ser variación de cosecha", "Si persiste dos cosechas, reentrenar", "6.7"),
    ("KS de la cosecha", "Modelo", 0.25, 0.20, "min",
     "Contrastar con el Gini antes de concluir", "Reentrenar", "6.7"),
    ("Observado / predicho", "Modelo", 1.15, 1.30, "max",
     "Recalibrar con la ventana más reciente", "Recalibrar y revisar el punto de corte", "6.7"),
    # El ECE se evalúa sobre ventana móvil de 12 meses, no por trimestre: con cosechas de ~300 créditos,
    # una calibración PERFECTA ya produce un ECE mediano de 0.046 por puro ruido muestral (simulación en
    # el notebook 11). Con ~1,200 créditos la mediana baja a 0.023 y el p95 a 0.033, que es de donde sale
    # el umbral verde. Medirlo por trimestre encendería alertas que no son deterioro.
    ("Error de calibración (ECE, ventana 12 meses)", "Modelo", 0.035, 0.05, "max",
     "Recalibrar", "Recalibrar y revisar bandas de score", "6.7"),
    ("Aprobación final", "Negocio", 0.65, 0.60, "min",
     "Revisar cola de revisión y capacidad de verificación", "Escalar al Comité: es objetivo de negocio, no límite de riesgo", "6.9"),
    ("Default 12m de la cosecha", "Negocio", 0.11, 0.13, "max",
     "Revisar calibración antes que el corte", "Bajar el umbral de aprobación automática y escalar al Comité", "6.1 y 6.9"),
    ("Pérdida esperada / monto", "Negocio", 0.0334, 0.0389, "max",
     "Revisar calibración y mezcla de la cartera", "Recortar la banda 580-600 y escalar al Comité", "6.12"),
    ("Cola de revisión manual", "Negocio", 0.20, 0.25, "max",
     "Priorizar por valor esperado", "Ampliar capacidad o ajustar umbrales", "6.9"),
    ("AIR por región y por efectivo", "Negocio", 0.80, 0.75, "min",
     "Revisar la política de verificación de ingreso", "Escalar al Comité: no se compensa con otras métricas", "6.8"),
]

COLUMNAS = ["indicador", "tipo", "verde", "ambar", "direccion", "accion_ambar", "accion_roja", "origen"]


def thresholds() -> pd.DataFrame:
    return pd.DataFrame(INDICADORES, columns=COLUMNAS).set_index("indicador")


def semaforo(indicador: str, valor: float, umbrales: pd.DataFrame | None = None) -> str:
    """Verde / Ámbar / Rojo según la dirección del indicador."""
    u = (umbrales if umbrales is not None else thresholds()).loc[indicador]
    if pd.isna(valor):
        return "Sin dato"
    if u["direccion"] == "max":
        return "Verde" if valor <= u["verde"] else ("Ámbar" if valor <= u["ambar"] else "Rojo")
    return "Verde" if valor >= u["verde"] else ("Ámbar" if valor >= u["ambar"] else "Rojo")


def cohort_metrics(base: pd.DataFrame, produccion: pd.DataFrame, pd_hat_base, pd_hat_prod, score_base, score_prod,
                   decisiones=None, el_sobre_monto=None, freq: str = "Q", target: str = cfg.TARGET) -> pd.DataFrame:
    """Indicadores por cosecha de producción, comparados contra la base de desarrollo.

    `base` es DEV (la referencia del PSI y de la banda de Gini) y `produccion`, las cosechas
    que se van cerrando. Con `decisiones` y `el_sobre_monto` se agregan los indicadores de negocio.
    """
    prod = produccion.copy()
    prod["_pd"] = np.asarray(pd_hat_prod, dtype=float)
    prod["_score"] = np.asarray(score_prod, dtype=float)
    if decisiones is not None:
        prod["_decision"] = np.asarray(decisiones, dtype=object)
    filas = []
    for periodo, g in prod.groupby(prod[cfg.DATE_COL].dt.to_period(freq)):
        y = g[target]
        fila = {"cosecha": str(periodo), "solicitudes": len(g), "defaults": int(y.sum()),
                "psi_score": validation.psi(pd.Series(score_base), g["_score"]),
                "psi_buro": validation.psi(base["bureau_score"], g["bureau_score"]),
                "faltantes_buro": float(g["bureau_score"].isna().mean()),
                "gini": validation.gini(y, g["_pd"]) if y.nunique() > 1 else np.nan,
                "ks": validation.ks_statistic(y, g["_pd"]) if y.nunique() > 1 else np.nan}
        if y.nunique() > 1:
            cal = ev.calibration_metrics(y, g["_pd"])
            fila.update({"observado_sobre_predicho": cal["observado_sobre_predicho"], "ece_trimestral": cal["ece"],
                         "default_cosecha": float(y.mean())})
            # Ventana móvil de 12 meses: el ECE trimestral está dominado por ruido muestral.
            fin = periodo.end_time
            ventana = prod[(prod[cfg.DATE_COL] <= fin) & (prod[cfg.DATE_COL] > fin - pd.DateOffset(months=12))]
            if ventana[target].nunique() > 1:
                fila["ece_movil_12m"] = ev.calibration_metrics(ventana[target], ventana["_pd"])["ece"]
                fila["creditos_ventana"] = len(ventana)
        if decisiones is not None:
            fila["revision"] = float((g["_decision"] == "REVIEW").mean())
            fila["aprobacion_automatica"] = float((g["_decision"] == "APPROVE").mean())
        if el_sobre_monto is not None:
            fila["el_sobre_monto"] = float(el_sobre_monto)
        filas.append(fila)
    return pd.DataFrame(filas).set_index("cosecha")


def traffic_light_report(metricas: pd.DataFrame, mapa: dict | None = None) -> pd.DataFrame:
    """Aplica los semáforos a la tabla de cosechas y devuelve el estado por indicador."""
    mapa = mapa or {"psi_score": "PSI del score", "psi_buro": "PSI de una variable del scorecard",
                    "faltantes_buro": "Tasa de faltantes de buró", "gini": "Gini de la cosecha",
                    "ks": "KS de la cosecha", "observado_sobre_predicho": "Observado / predicho",
                    "ece": "Error de calibración (ECE)", "default_cosecha": "Default 12m de la cosecha",
                    "revision": "Cola de revisión manual", "el_sobre_monto": "Pérdida esperada / monto"}
    u = thresholds()
    filas = []
    for columna, indicador in mapa.items():
        if columna not in metricas.columns:
            continue
        for cosecha, valor in metricas[columna].items():
            filas.append({"cosecha": cosecha, "indicador": indicador, "tipo": u.loc[indicador, "tipo"],
                          "valor": valor, "semaforo": semaforo(indicador, valor, u)})
    t = pd.DataFrame(filas)
    return t.pivot(index=["tipo", "indicador"], columns="cosecha", values="semaforo").sort_index()


def alert_actions(estado: pd.DataFrame) -> pd.DataFrame:
    """Para cada indicador con alerta, la acción que corresponde y quién la ejecuta."""
    u = thresholds()
    filas = []
    for (tipo, indicador), fila in estado.iterrows():
        peor = "Rojo" if (fila == "Rojo").any() else ("Ámbar" if (fila == "Ámbar").any() else "Verde")
        if peor == "Verde":
            continue
        filas.append({"tipo": tipo, "indicador": indicador, "estado": peor,
                      "cosechas_en_alerta": ", ".join(fila.index[fila == peor]),
                      "accion": u.loc[indicador, "accion_roja" if peor == "Rojo" else "accion_ambar"],
                      "responsable": "Analytics" if tipo in ("Datos", "Modelo") else "Riesgos y Negocio",
                      "origen": u.loc[indicador, "origen"]})
    return pd.DataFrame(filas)


CALENDARIO = [
    ("Diario", "Datos y operación", "Volumen, tasa de faltantes, errores del servicio, latencia", "Analytics / TI"),
    ("Mensual", "Datos y negocio", "PSI del score y de variables, mezcla de decisiones, cola de revisión, AIR", "Analytics"),
    ("Trimestral", "Modelo y negocio", "Gini, KS, calibración y EL de la cosecha cerrada; semáforo del apetito", "Riesgos"),
    ("Anual", "Gobierno", "Validación independiente completa, revisión de la Model Card y del apetito", "Validación y Comité"),
]


def calendario() -> pd.DataFrame:
    return pd.DataFrame(CALENDARIO, columns=["frecuencia", "alcance", "qué se revisa", "responsable"])


# Escalera de acciones ante alerta (6.15): cada peldaño se activa solo si el anterior no alcanza.
ESCALERA = [
    ("1. Investigar", "Cualquier indicador en ámbar", "Analytics",
     "Diagnóstico en 5 días hábiles; el modelo no se toca"),
    ("2. Recalibrar", "Observado/predicho fuera de [0.85, 1.15] dos meses, o pérdida esperada sobre 3.34%",
     "Analytics; aprueba Jefatura de Riesgos", "Nuevo calibrador Platt con la ventana reciente; el orden del score no cambia"),
    ("3. Reentrenar", "Gini bajo 0.30 dos cosechas seguidas, o PSI del score sobre 0.25 por cambio estructural",
     "Analytics; valida Validación independiente", "El modelo nuevo entra como challenger y no reemplaza sin validación"),
    ("4. Limitar uso", "Falla de una fuente crítica (buró) o AIR bajo 0.75 en algún segmento",
     "Jefatura de Riesgos", "Se suspende la aprobación automática del segmento afectado: todo pasa a revisión"),
    ("5. Rollback", "El champion recién promovido empeora en su primera cosecha, o falla la integridad del artefacto",
     "Jefatura de Riesgos, registrado", "Se repromueve el champion anterior en el Model Registry (registry.promote)"),
    ("6. Retiro", "Deterioro que no corrigen ni la recalibración ni el reentrenamiento, o cambio de producto o regulación",
     "Comité de Riesgos", "El modelo pasa a 'retirado' en el inventario y la decisión vuelve a reglas con revisión experta"),
]


def escalera_de_acciones() -> pd.DataFrame:
    return pd.DataFrame(ESCALERA, columns=["acción", "se activa cuando", "decide", "qué ocurre"])
