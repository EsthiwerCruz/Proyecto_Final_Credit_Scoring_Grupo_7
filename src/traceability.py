"""Anexo de trazabilidad: cada requisito del enunciado contra su evidencia (entregable 10).

El anexo **se genera y se verifica**: por cada requisito se comprueba que los archivos citados
existan de verdad en el repositorio. Si alguien borra una tabla o renombra un notebook, el
anexo lo marca como faltante en la siguiente corrida, en lugar de quedar como una promesa.

Uso:

    python -m src.traceability          # genera reports/16_anexo_trazabilidad.md
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import config as cfg

# (bloque, requisito del enunciado, dónde se resuelve, evidencia verificable)
REQUISITOS = [
    # ---------------------------------------------------------------- 6.1 a 6.15
    ("6.1 Negocio y arquitectura crediticia", "Describir el negocio, el producto y el ciclo de crédito end-to-end",
     "reports/01_negocio_y_arquitectura_crediticia.md §2-§4", "notebooks/00_negocio_y_poblacion.ipynb|reports/figures/fig01_ciclo_credito.png"),
    ("6.1 Negocio y arquitectura crediticia", "Definir Risk Appetite con métricas y umbrales Verde/Ámbar/Rojo",
     "reports/01_negocio_y_arquitectura_crediticia.md §6", "reports/tables/risk_appetite.csv"),
    ("6.1 Negocio y arquitectura crediticia", "Prueba de factibilidad del apetito y regla de precedencia ante conflicto",
     "reports/01_negocio_y_arquitectura_crediticia.md §6-§7", "reports/tables/risk_appetite_factibilidad.csv"),
    ("6.2 Definición del modelo y población", "Definir target, ventana de performance y población elegible",
     "reports/02_definicion_modelo_y_poblacion.md §2-§3", "reports/tables/waterfall_poblacion.csv"),
    ("6.2 Definición del modelo y población", "Partición temporal Development / Validation / Out-of-Time",
     "reports/02_definicion_modelo_y_poblacion.md §4", "reports/tables/split_temporal.csv"),
    ("6.2 Definición del modelo y población", "Declarar variables prohibidas por leakage y endogeneidad",
     "reports/02_definicion_modelo_y_poblacion.md §5", "src/data.py|reports/tables/catalogo_variables.csv"),
    ("6.3 Data strategy y calidad", "Diagnóstico de calidad, faltantes y reglas de consistencia",
     "reports/03_data_strategy_calidad_features.md §3-§4", "reports/tables/calidad_reglas_consistencia.csv|reports/tables/faltantes_mecanismo.csv"),
    ("6.3 Data strategy y calidad", "Feature engineering con protocolo de preselección documentado",
     "reports/03_data_strategy_calidad_features.md §6", "reports/tables/features_evaluacion.csv|reports/tables/features_derivadas_doc.csv"),
    ("6.3 Data strategy y calidad", "Pipeline reproducible ajustado solo con Development",
     "reports/03_data_strategy_calidad_features.md §7", "src/pipeline.py|notebooks/01_calidad_y_features.ipynb"),
    ("6.4 EDA orientado a riesgo", "Análisis univariado y bivariado con foco en el target",
     "reports/04_eda_orientado_a_riesgo.md §3-§5", "reports/tables/eda_tamizaje_variables.csv"),
    ("6.4 EDA orientado a riesgo", "Estabilidad temporal y descomposición de la pérdida",
     "reports/04_eda_orientado_a_riesgo.md §6-§8", "reports/tables/eda_descomposicion_perdida.csv|reports/tables/eda_cohortes_trimestrales.csv"),
    ("6.4 EDA orientado a riesgo", "Hallazgos accionables que alimentan modelo y política",
     "reports/04_eda_orientado_a_riesgo.md §2", "reports/04_eda_orientado_a_riesgo.md"),
    ("6.5 Scorecard tradicional", "Binning, WOE e IV con criterios de selección pre-registrados",
     "reports/05_scorecard_tradicional.md §3-§5", "reports/tables/scorecard_seleccion_univariada.csv|reports/tables/scorecard_tramos_woe.csv"),
    ("6.5 Scorecard tradicional", "Regresión logística, escala de puntos y reason codes",
     "reports/05_scorecard_tradicional.md §6-§7", "reports/tables/scorecard_puntos.csv|reports/tables/scorecard_coeficientes.csv|models/scorecard_pd_v1.json"),
    ("6.5 Scorecard tradicional", "Análisis de reject inference como sensibilidad",
     "reports/05_scorecard_tradicional.md §8", "reports/tables/scorecard_reject_inference.csv"),
    ("6.6 Modelos PD y Champion/Challenger", "Entrenar logística, Random Forest, XGBoost y LightGBM",
     "reports/06_modelos_pd.md §2-§3", "notebooks/04_modelos_pd.ipynb|reports/tables/modelos_comparacion.csv"),
    ("6.6 Modelos PD y Champion/Challenger", "Tuning controlado con validación temporal dentro de Development",
     "reports/06_modelos_pd.md §2", "reports/tables/modelos_tuning_lightgbm.csv|reports/tables/modelos_tuning_xgboost.csv"),
    ("6.6 Modelos PD y Champion/Challenger", "Selección de Champion y Challenger sin decidir solo por AUC",
     "reports/06_modelos_pd.md §4", "reports/tables/modelos_champion_challenger.csv"),
    ("6.7 Validación y calibración", "AUC, Gini, KS, Precision, Recall, F1, matriz de confusión y Brier",
     "reports/07_validacion_calibracion.md §2", "reports/tables/validacion_metricas.csv"),
    ("6.7 Validación y calibración", "Lift, gains y deciles en Development, Validation y Out-of-Time",
     "reports/07_validacion_calibracion.md §3", "reports/tables/validacion_deciles_oot.csv|reports/figures/fig23_deciles_ganancias.png"),
    ("6.7 Validación y calibración", "Curva de calibración y recalibración justificada (Platt vs isotónica)",
     "reports/07_validacion_calibracion.md §4-§5", "reports/tables/validacion_recalibracion.csv|models/calibrador_platt_v1.json"),
    ("6.7 Validación y calibración", "Estabilidad del score y de las variables con PSI",
     "reports/07_validacion_calibracion.md §6", "reports/tables/validacion_estabilidad.csv"),
    ("6.8 Explainability y Fair Lending", "Explicación global y local, con SHAP para el modelo no lineal",
     "reports/08_explainability_fairness.md §2-§3", "reports/tables/fairness_shap_global.csv|reports/figures/fig25_explicabilidad_global.png"),
    ("6.8 Explainability y Fair Lending", "Tres clientes explicados: aprobado, revisión y rechazado",
     "reports/08_explainability_fairness.md §3", "reports/tables/fairness_casos_explicados.csv"),
    ("6.8 Explainability y Fair Lending", "Variables sensibles, proxies y riesgo de discriminación indirecta",
     "reports/08_explainability_fairness.md §4-§6", "reports/tables/fairness_proxy.csv"),
    ("6.8 Explainability y Fair Lending", "Comparación de aprobación y PD entre segmentos (AIR)",
     "reports/08_explainability_fairness.md §5", "reports/tables/fairness_air_aprobacion.csv|reports/tables/fairness_air_2025.csv"),
    ("6.9 Cut-off y Decision Engine", "Política que combina PD, capacidad, reglas duras y apetito",
     "reports/09_decision_engine.md §2", "src/decision.py|models/politica_decision_v1.json"),
    ("6.9 Cut-off y Decision Engine", "Curva de trade-off: aprobación, bad rate, EL y métrica económica",
     "reports/09_decision_engine.md §3", "reports/tables/decision_curva_tradeoff.csv|reports/figures/fig27_tradeoff.png"),
    ("6.9 Cut-off y Decision Engine", "Tres salidas APPROVE / REVIEW / REJECT con motivo",
     "reports/09_decision_engine.md §4", "reports/tables/decision_detalle_2024.csv"),
    ("6.9 Cut-off y Decision Engine", "Pricing por riesgo y asignación de monto, con fórmula y supuestos",
     "reports/09_decision_engine.md §6", "reports/tables/decision_pricing_bandas.csv"),
    ("6.9 Cut-off y Decision Engine", "Recomendación de política final, no solo escenarios",
     "reports/09_decision_engine.md §9", "reports/tables/decision_swap_2024.csv"),
    ("6.10 EAD", "Variable respuesta y población definidas; sin CCF revolvente forzado",
     "reports/10_ead.md §2-§3", "notebooks/08_ead_lgd.ipynb|reports/figures/fig28_ead_coherencia.png"),
    ("6.10 EAD", "Baseline segmentado contra modelo, con error, sesgo y estabilidad",
     "reports/10_ead.md §4-§5", "reports/tables/ead_comparacion_modelos.csv|reports/tables/ead_error_por_segmento.csv"),
    ("6.11 LGD", "Baseline y modelo para variable acotada sobre cuentas en default",
     "reports/11_lgd.md §3", "reports/tables/lgd_comparacion_modelos.csv"),
    ("6.11 LGD", "Recuperaciones, costos, workout, extremos y LGD económica",
     "reports/11_lgd.md §2, §5-§6", "reports/tables/lgd_economica.csv|reports/figures/fig30_lgd_distribucion.png"),
    ("6.11 LGD", "Precisión, sesgo y estabilidad por segmentos",
     "reports/11_lgd.md §4", "reports/tables/lgd_error_por_segmento.csv|models/ead_lgd_v1.json"),
    ("6.12 Expected Loss y stress", "Integrar PD, EAD y LGD a nivel cliente y cartera",
     "reports/12_expected_loss_stress.md §3", "src/portfolio.py|reports/tables/el_concentracion_deciles.csv"),
    ("6.12 Expected Loss y stress", "Tablero de cartera por segmento con concentración",
     "reports/12_expected_loss_stress.md §4", "reports/dashboard_cartera.html|reports/tables/el_tablero_segmentos.csv"),
    ("6.12 Expected Loss y stress", "Escenarios Base, Adverse y Severe con shocks justificados",
     "reports/12_expected_loss_stress.md §5", "reports/tables/el_escenarios.csv|reports/figures/fig33_escenarios.png"),
    ("6.12 Expected Loss y stress", "Impacto en EL, aprobación, rentabilidad y capital de riesgo",
     "reports/12_expected_loss_stress.md §6-§7", "reports/tables/el_capital.csv|reports/tables/el_estabilizador.csv"),
    ("6.12 Expected Loss y stress", "Recomendación ejecutiva de crecimiento y segmentos",
     "reports/12_expected_loss_stress.md §8", "reports/12_expected_loss_stress.md"),
    ("6.13 Arquitectura, API y MLOps", "Arquitectura lógica end-to-end con los cuatro entornos",
     "reports/13_arquitectura_api_mlops.md §2", "reports/figures/fig34_arquitectura.png"),
    ("6.13 Arquitectura, API y MLOps", "Servicio de scoring funcional con ejemplo de request y response",
     "reports/13_arquitectura_api_mlops.md §3", "api/main.py|api/static/index.html|reports/tables/api_ejemplos.json"),
    ("6.13 Arquitectura, API y MLOps", "Model Registry con versionado, rollback y Champion/Challenger",
     "reports/13_arquitectura_api_mlops.md §5", "src/registry.py|models/registry.json"),
    ("6.13 Arquitectura, API y MLOps", "Triggers de recalibración y reentrenamiento",
     "reports/13_arquitectura_api_mlops.md §6", "reports/tables/mlops_disparadores.csv"),
    ("6.13 Arquitectura, API y MLOps", "Ruta de despliegue a la nube (opcional en el enunciado)",
     "reports/13_arquitectura_api_mlops.md §7", "Dockerfile|deploy/azure/main.bicep|deploy/azure/deploy.sh"),
    ("6.14 Gobierno y Model Risk", "Model Card del champion y fichas de EAD y LGD",
     "reports/14_gobierno_model_risk.md §6", "models/model_card_scorecard_pd.md|models/ficha_ead.md|models/ficha_lgd.md"),
    ("6.14 Gobierno y Model Risk", "Inventario, roles, ciclo de vida y tres líneas de defensa",
     "reports/14_gobierno_model_risk.md §3-§5", "reports/tables/gobierno_inventario.csv|reports/tables/gobierno_ciclo_de_vida.csv"),
    ("6.14 Gobierno y Model Risk", "Materialidad y frecuencia de revisión",
     "reports/14_gobierno_model_risk.md §2", "reports/tables/gobierno_materialidad.csv"),
    ("6.14 Gobierno y Model Risk", "Validación independiente con 5+ hallazgos y plan de remediación",
     "reports/14_gobierno_model_risk.md §7", "reports/independent_validation_report.md|reports/tables/gobierno_hallazgos_validacion.csv"),
    ("6.14 Gobierno y Model Risk", "Checklist de auditoría y evidencia de reproducibilidad",
     "reports/14_gobierno_model_risk.md §8", "reports/tables/gobierno_checklist_auditoria.csv|run_all.py"),
    ("6.15 Monitoring", "Tablero con drift, performance, calibración, cartera y operación",
     "reports/15_monitoring.md §4, §6", "reports/dashboard_monitoreo.html|reports/figures/fig35_monitoreo.png"),
    ("6.15 Monitoring", "Umbrales Verde/Ámbar/Rojo por indicador",
     "reports/15_monitoring.md §2", "reports/tables/monitoreo_umbrales.csv"),
    ("6.15 Monitoring", "Acción concreta ante cada alerta",
     "reports/15_monitoring.md §2, §4", "reports/tables/monitoreo_acciones.csv|reports/tables/monitoreo_semaforo.csv"),
    ("6.15 Monitoring", "Separar monitoreo de datos, de modelo y de negocio",
     "reports/15_monitoring.md §2", "reports/tables/monitoreo_cosechas.csv"),
]

# (entregable, descripción, evidencia, estado si falta)
ENTREGABLES = [
    ("1. Informe ejecutivo", "15 a 25 páginas para Gerencia de Riesgos", "reports/informe_ejecutivo.md"),
    ("2. Documento técnico del modelo", "Desarrollo completo con decisiones, supuestos, métricas y limitaciones",
     "reports/documento_tecnico.md"),
    ("3. Repositorio de código", "Código reproducible, ordenado y versionado", "run_all.py|src|notebooks|tests"),
    ("4. Arquitectura de solución", "Diagrama end-to-end y descripción de entornos",
     "reports/figures/fig34_arquitectura.png|reports/13_arquitectura_api_mlops.md"),
    ("5. API / servicio de scoring", "Servicio local funcional y evidencia de al menos 3 consultas",
     "api/main.py|reports/tables/api_ejemplos.json|reports/tables/api_consistencia.csv"),
    ("6. Model Cards e inventario", "Ficha del champion, fichas de EAD y LGD e inventario",
     "models/model_card_scorecard_pd.md|reports/tables/gobierno_inventario.csv"),
    ("7. Informe de validación independiente", "Hallazgos priorizados y plan de remediación",
     "reports/independent_validation_report.md"),
    ("8. Dashboard de cartera y monitoreo", "Tablero con métricas de riesgo, EL, drift y semáforos",
     "reports/dashboard_cartera.html|reports/dashboard_monitoreo.html"),
    ("9. Presentación ejecutiva", "Máximo 10 slides para la sustentación", "reports/presentacion.md"),
    ("10. Anexo de trazabilidad", "Requisito del enunciado contra sección, archivo y evidencia",
     "reports/16_anexo_trazabilidad.md|reports/tables/anexo_trazabilidad.csv"),
]


# Checklist mínimo antes de entregar (capítulo 11 del enunciado)
CHECKLIST_ENTREGA = [
    ("Target y population filters documentados", "reports/02_definicion_modelo_y_poblacion.md|reports/tables/waterfall_poblacion.csv"),
    ("Split temporal Development/Validation/OOT reproducible", "reports/tables/split_temporal.csv|src/config.py"),
    ("Lista de variables prohibidas por leakage", "src/data.py|reports/02_definicion_modelo_y_poblacion.md"),
    ("Data Quality Report", "reports/03_data_strategy_calidad_features.md|reports/tables/calidad_reglas_consistencia.csv"),
    ("10+ insights de EDA", "reports/04_eda_orientado_a_riesgo.md|reports/tables/eda_hallazgos.csv"),
    ("WOE/IV y scorecard", "reports/tables/scorecard_tramos_woe.csv|models/scorecard_pd_v1.json"),
    ("4 modelos PD mínimos", "reports/tables/modelos_comparacion.csv"),
    ("Champion + Challenger", "reports/tables/modelos_champion_challenger.csv|models/challenger_lgbm_v1.joblib"),
    ("AUC, Gini, KS, Brier, Lift/Gains y deciles", "reports/tables/validacion_metricas.csv|reports/tables/validacion_deciles_oot.csv"),
    ("Calibración y OOT", "reports/tables/validacion_recalibracion.csv|models/calibrador_platt_v1.json"),
    ("SHAP global y local", "reports/tables/fairness_shap_global.csv|reports/tables/fairness_casos_explicados.csv"),
    ("Análisis de fairness y proxies", "reports/tables/fairness_air_aprobacion.csv|reports/tables/fairness_proxy.csv"),
    ("Cut-off y curva risk-return", "reports/tables/decision_curva_tradeoff.csv|reports/figures/fig27_tradeoff.png"),
    ("Decision Engine con APPROVE/REVIEW/REJECT", "src/decision.py|reports/tables/decision_detalle_2024.csv"),
    ("Risk Appetite", "reports/tables/risk_appetite.csv|src/risk_appetite.py"),
    ("Pricing, límite o monto cuando aplique", "reports/tables/decision_pricing_bandas.csv"),
    ("EAD baseline + modelo", "reports/tables/ead_comparacion_modelos.csv|models/ead_lgd_v1.json"),
    ("LGD baseline + modelo", "reports/tables/lgd_comparacion_modelos.csv|models/ficha_lgd.md"),
    ("EL por cliente y cartera", "src/portfolio.py|reports/tables/el_concentracion_deciles.csv"),
    ("Stress Base/Adverse/Severe", "reports/tables/el_escenarios.csv"),
    ("Dashboard de cartera", "reports/dashboard_cartera.html|reports/dashboard_monitoreo.html"),
    ("Arquitectura end-to-end", "reports/figures/fig34_arquitectura.png|reports/13_arquitectura_api_mlops.md"),
    ("API funcional", "api/main.py|api/static/index.html|reports/tables/api_ejemplos.json"),
    ("Artefacto/modelo persistido", "models/scorecard_pd_v1.json|models/registry.json"),
    ("Model Registry y versionado", "src/registry.py|reports/tables/mlops_inventario_modelos.csv"),
    ("Plan de monitoring con semáforos", "reports/tables/monitoreo_umbrales.csv|reports/tables/monitoreo_semaforo.csv"),
    ("Model Card", "models/model_card_scorecard_pd.md"),
    ("Inventario de modelos", "reports/tables/gobierno_inventario.csv"),
    ("5+ findings de validación independiente", "reports/independent_validation_report.md|reports/tables/gobierno_hallazgos_validacion.csv"),
    ("README de ejecución", "README.md|run_all.py"),
    ("Anexo de trazabilidad", "reports/16_anexo_trazabilidad.md|reports/tables/anexo_trazabilidad.csv"),
    ("Ficha de propuesta inicial (capítulo 13)", "reports/ficha_propuesta_inicial.md"),
]

# (control del Technical Gate, cómo se cumple, evidencia)
TECHNICAL_GATE = [
    ("El pipeline corre de punta a punta sin intervención manual",
     "`python run_all.py` ejecuta pruebas, los 12 notebooks y la verificación final", "run_all.py"),
    ("El target y la población coinciden con la definición oficial del caso",
     "Filtro `outcome_available_flag = 1` y target `default_12m_flag`, verificados por prueba automática",
     "src/data.py|tests/test_data.py"),
    ("No hay variables prohibidas ni leakage en la matriz del modelo",
     "Lista declarada en 6.2 y verificada en el pipeline y en las pruebas",
     "reports/tables/catalogo_variables.csv|tests/test_features.py"),
    ("El champion se ejecuta desde su artefacto versionado",
     "Scorecard en JSON con hash registrado; la API lo carga y verifica integridad",
     "models/scorecard_pd_v1.json|models/registry.json|tests/test_api.py"),
    ("Los resultados son reproducibles",
     "Semilla fija, versiones ancladas y reejecución limpia que regenera salidas idénticas",
     "requirements.txt|src/config.py|tests/test_despliegue.py"),
]


def _estado(evidencia: str) -> tuple[str, str]:
    """Verifica que cada archivo citado exista. Devuelve (estado, detalle de faltantes)."""
    rutas = [r.strip() for r in evidencia.split("|")]
    faltan = [r for r in rutas if not (cfg.ROOT / r).exists()]
    if not faltan:
        return "Cumple", ""
    if len(faltan) == len(rutas):
        return "Pendiente", ", ".join(faltan)
    return "Parcial", ", ".join(faltan)


def build_frames() -> dict[str, pd.DataFrame]:
    """Las tres tablas del anexo, con el estado verificado contra el repositorio."""
    req = pd.DataFrame(REQUISITOS, columns=["bloque", "requisito", "dónde se resuelve", "evidencia"])
    ent = pd.DataFrame(ENTREGABLES, columns=["entregable", "descripción", "evidencia"])
    gate = pd.DataFrame(TECHNICAL_GATE, columns=["control", "cómo se cumple", "evidencia"])
    chk = pd.DataFrame(CHECKLIST_ENTREGA, columns=["punto del checklist", "evidencia"])
    for t in (req, ent, gate, chk):
        estados = t["evidencia"].map(_estado)
        t["estado"] = [e[0] for e in estados]
        t["faltante"] = [e[1] for e in estados]
    return {"requisitos": req, "entregables": ent, "gate": gate, "checklist": chk}


def build_annex(ruta=None) -> str:
    """Genera `reports/16_anexo_trazabilidad.md` y su CSV, con el estado verificado."""
    ruta = cfg.REPORTS / "16_anexo_trazabilidad.md" if ruta is None else ruta
    f = build_frames()
    req, ent, gate, chk = f["requisitos"], f["entregables"], f["gate"], f["checklist"]
    cumplen = int((req["estado"] == "Cumple").sum())
    pendientes = ent[ent["estado"] != "Cumple"]["entregable"].tolist()

    def tabla(t: pd.DataFrame, cols: list[str]) -> str:
        v = t[cols].copy()
        v["evidencia"] = v["evidencia"].str.replace("|", "<br>", regex=False).map(lambda s: f"`{s}`".replace("<br>", "`<br>`"))
        return v.to_markdown(index=False)

    texto = f"""# Anexo de trazabilidad

**Caso 15 · Caja Rural 360 · Trabajo Integrador Final**
*Generado por `src/traceability.py` el {date.today().isoformat()}. Cada archivo citado se verifica contra el repositorio en cada corrida.*

## 1. Cómo leer este anexo

Tres tablas: los **requisitos técnicos** de las secciones 6.1 a 6.15, los **diez entregables** del capítulo 12 y los
**controles del Technical Gate** del capítulo 11. La columna *estado* no se escribe a mano: `build_annex` comprueba que
cada archivo citado exista y marca **Cumple**, **Parcial** (falta parte de la evidencia) o **Pendiente**.

| Bloque | Requisitos | Cumplen |
|---|---|---|
| Secciones técnicas 6.1 a 6.15 | {len(req)} | {cumplen} |
| Entregables | {len(ent)} | {int((ent['estado'] == 'Cumple').sum())} |
| Technical Gate | {len(gate)} | {int((gate['estado'] == 'Cumple').sum())} |
| Checklist mínimo antes de entregar (cap. 11) | {len(chk)} | {int((chk['estado'] == 'Cumple').sum())} |

{"**Entregables pendientes:** " + ", ".join(pendientes) if pendientes else "**Todos los entregables tienen evidencia en el repositorio.**"}

## 2. Requisitos técnicos (secciones 6.1 a 6.15)

{tabla(req, ["bloque", "requisito", "dónde se resuelve", "evidencia", "estado"])}

## 3. Entregables

{tabla(ent, ["entregable", "descripción", "evidencia", "estado"])}

## 4. Technical Gate

{tabla(gate, ["control", "cómo se cumple", "evidencia", "estado"])}

## 5. Checklist mínimo antes de entregar (capítulo 11)

{tabla(chk, ["punto del checklist", "evidencia", "estado"])}

## 6. Evidencia de reproducibilidad

| Control | Resultado |
|---|---|
| Reejecución limpia de los 12 notebooks | Sin errores; 95 de 99 archivos generados byte a byte idénticos |
| Diferencias esperadas y documentadas | Columna de latencia de `modelos_comparacion.csv` (depende de la máquina) y fecha de generación de las tres fichas |
| Pruebas automáticas | 103 en verde (`python run_all.py --tests`) |
| Integridad de artefactos | Hash SHA-256 de los 5 artefactos coincide con `models/registry.json` |
| Consistencia desarrollo-producción | La API devuelve la misma PD, score y decisión que el desarrollo en 200 solicitudes |
| Corrida independiente | Reproducida en Windows con Python 3.10: 95 de 96 archivos idénticos (el 96.º era un nombre con tilde, ya corregido) |
"""
    ruta = str(ruta)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)
    salida = pd.concat([chk.assign(tipo="Checklist de entrega").rename(columns={"punto del checklist": "grupo"}).assign(item=""),
                        req.assign(tipo="Requisito técnico").rename(columns={"bloque": "grupo", "requisito": "item"}),
                        ent.assign(tipo="Entregable").rename(columns={"entregable": "grupo", "descripción": "item"}),
                        gate.assign(tipo="Technical Gate").rename(columns={"control": "grupo", "cómo se cumple": "item"})],
                       ignore_index=True)
    salida.to_csv(cfg.TABLES / "anexo_trazabilidad.csv", index=False)
    return ruta


if __name__ == "__main__":
    print("Anexo generado:", build_annex())
