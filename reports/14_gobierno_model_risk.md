# 6.14 · Gobierno y Model Risk Management

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/11_gobierno_monitoreo.ipynb`; código en `src/governance.py` y `src/registry.py`; **Model Card** en `models/model_card_scorecard_pd.md`; fichas en `models/ficha_ead.md` y `ficha_lgd.md`; **informe de validación** en `reports/independent_validation_report.md`; tablas `gobierno_*.csv`.

---

## 1. Resumen

- **Materialidad Tier 1** (16 de 18 puntos): el modelo decide sobre el 100% de las solicitudes y aprueba o rechaza sin intervención humana en cerca del 77% de los casos. Corresponde validación independiente **anual**, monitoreo trimestral y reporte al Comité.
- **Model Card generada automáticamente** desde los artefactos y las tablas de resultados: no puede quedar desactualizada respecto del modelo que corre en producción.
- **Inventario de cinco artefactos** con versión, estado, dueño y hash SHA-256, verificable en caliente desde `/health`.
- **Validación independiente simulada con 10 hallazgos**: 2 de severidad alta, 5 media, 2 baja y 1 informativo, cada uno con evidencia, impacto, recomendación, responsable y plazo.
- **Conclusión de la validación:** apto para uso **con condiciones**; los dos hallazgos altos (coherencia de la EAD y vigencia de la calibración) deben remediarse antes del despliegue.
- **Checklist de auditoría de 10 controles**, nueve con evidencia verificable en el repositorio. El único pendiente es el acta del Comité, que es un acto de gobierno de la entidad y no algo que el equipo pueda producir.

## 2. Materialidad y frecuencia de revisión

| Criterio | Situación en este modelo | Puntaje |
|---|---|---|
| Exposición gestionada | Decide sobre el 100% de las solicitudes del producto | 3 |
| Automatización de la decisión | Aprueba y rechaza sin intervención humana en ~77% de los casos | 3 |
| Impacto en resultados | Determina pérdida esperada y pricing de toda la originación | 3 |
| Exposición regulatoria y reputacional | Decisión de crédito a personas; sujeto a fair lending | 3 |
| Complejidad del modelo | Scorecard lineal de 3 características, interpretable | 1 |
| Dependencia de terceros | Una fuente externa crítica: el score de buró | 2 |
| **Total** | | **16 de 18 · Tier 1 (alta)** |

Lo único que baja el puntaje es que el modelo es simple e interpretable. **La simplicidad del modelo no reduce su materialidad**: lo que pesa es qué decide y sobre cuánta cartera.

## 3. Ciclo de vida y roles de aprobación

| Etapa | Contenido | Ejecuta | Aprueba |
|---|---|---|---|
| 1. Propuesta | Caso de negocio, población y target | Analytics | Jefatura de Riesgos |
| 2. Desarrollo | Datos, features, modelo y política (6.1 a 6.9) | Analytics | — |
| 3. Validación independiente | Revisión metodológica y hallazgos | Validación | Validación firma |
| 4. Aprobación | Decisión de uso, apetito y umbrales | Comité de Riesgos | Comité de Riesgos |
| 5. Despliegue | Promoción en el Model Registry y publicación de la API | Analytics + TI | Jefatura de Riesgos |
| 6. Monitoreo | Datos, modelo y negocio con semáforos (6.15) | Analytics y Riesgos | — |
| 7. Recalibración / reentrenamiento | **Disparado por umbrales, no por calendario** | Analytics | Validación |
| 8. Retiro o rollback | Degradación del champion y promoción del anterior | Comité de Riesgos | Comité de Riesgos |

## 4. Tres líneas de defensa

| Línea | Quién | Responsabilidad | Evidencia que produce |
|---|---|---|---|
| Primera | Analytics y Negocio | Construye el modelo y la política, ejecuta el monitoreo operativo y documenta | Model Card, tablero de monitoreo, registro de decisiones |
| Segunda | Riesgos y Validación independiente | Desafía la metodología, valida antes del uso, aprueba cambios de champion y vigila el apetito | Informe de validación, semáforo del apetito, actas del Comité |
| Tercera | Auditoría interna | Comprueba que el marco se cumpla y que todo sea reproducible y trazable | Checklist de auditoría, hash de artefactos, reejecución del repositorio |

## 5. Inventario de modelos

| Artefacto | Versión | Estado | Sección | Entrenado con |
|---|---|---|---|---|
| `scorecard_pd_v1.json` | 1.0 | **champion** | 6.5 | DEV 2021-2023 |
| `challenger_lgbm_v1.joblib` | 1.0 | challenger | 6.6 | DEV 2021-2023 |
| `calibrador_platt_v1.json` | 1.0 | soporte | 6.7 | VAL 2024 |
| `politica_decision_v1.json` | 1.0 | soporte | 6.9 | — |
| `ead_lgd_v1.json` | 1.0 | soporte | 6.10 y 6.11 | DEV 2021-2023 |

Cada entrada guarda además dueño, fecha de registro, tamaño y **SHA-256**. `GET /health` recalcula los hashes y reporta cualquier diferencia: es el control mínimo de integridad para que un validador pueda confiar en que el modelo documentado es el que corre.

## 6. Model Card y fichas

- **`models/model_card_scorecard_pd.md`** (champion): identificación y hash, propósito y **usos no previstos**, datos y variables, metodología y escala, desempeño en DEV/VAL/OOT, fairness, limitaciones, monitoreo y disparadores, gobierno y reproducibilidad.
- **`models/ficha_ead.md`** y **`models/ficha_lgd.md`**: variable respuesta, población, método, parámetro adoptado, error en VAL, confirmación en OOT, limitación principal y uso aguas abajo.

Las tres se **generan desde los artefactos y las tablas** con `governance.build_model_card` y `build_short_card`, así que se regeneran con cada corrida del proyecto. Una Model Card escrita a mano se desactualiza en la primera recalibración; esta no puede.

## 7. Validación independiente simulada

**Alcance.** Definición de target y población, partición temporal, tratamiento de datos, construcción y selección del scorecard, calibración, fairness, motor de decisión, parámetros de EAD y LGD, integración en pérdida esperada y servicio de scoring. Se reejecutó el repositorio completo, se verificó la integridad de los artefactos y se contrastaron las cifras de los reportes contra las tablas generadas.

**Hallazgos** (detalle completo en `reports/independent_validation_report.md`):

| Id | Severidad | Hallazgo | Responsable | Plazo |
|---|---|---|---|---|
| V-01 | **Alta** | La exposición al default no es coherente con el calendario de amortización (49.3% de los defaults implica más de 12 cuotas) | Dueño del dato + Analytics | Antes del despliegue |
| V-02 | **Alta** | La calibración envejece rápido: sin corrección, la PD subestima ~30% | Analytics | Trimestral, permanente |
| V-03 | Media | EAD y LGD constantes sobre 351 defaults; no hay muestra para segmentar | Analytics | Revisión anual |
| V-04 | Media | Impacto adverso en el quintil de mayor ingreso en efectivo (AIR 0.74 en 2024 y 2025) | Riesgos | Mensual |
| V-05 | Media | La cola de revisión manual (23.2%) excede la capacidad declarada (20%) | Operaciones + Riesgos | Antes del despliegue |
| V-06 | Media | El supuesto de aprobación del 60% de las revisiones no está validado | Operaciones | Primer trimestre de uso |
| V-07 | Media | Concentración en un solo proveedor: el buró explica el 64% del rango de puntos | TI + Riesgos | Antes del despliegue |
| V-08 | Baja | El challenger superó al champion en OOT sin significancia estadística | Analytics | Revisión semestral |
| V-09 | Baja | No se aplicó reject inference al champion | Analytics | A los 12 meses de uso |
| V-10 | Informativo | Datos sintéticos: la severidad no se comporta como una cartera real | Analytics + Validación | Antes de producción real |

**Conclusión de la validación:** *apto para uso con condiciones*. La metodología es sólida y reproducible —partición temporal respetada, OOT usado una sola vez, sin leakage, y el servicio responde exactamente lo mismo que el desarrollo—. Los hallazgos se concentran en la **calidad del dato de exposición**, la **vigencia de la calibración** y **supuestos operativos de la política**, no en la construcción del modelo.

## 8. Checklist mínimo de auditoría

| Control | Evidencia verificable | Estado |
|---|---|---|
| Reproducibilidad | `python run_all.py` regenera tablas, figuras y artefactos idénticos | Cumple |
| Integridad de artefactos | Hash SHA-256 contra el Model Registry (`/health`) | Cumple |
| Trazabilidad de decisiones | `trace_id` y versión de modelo, calibrador y política en cada respuesta | Cumple |
| Separación de muestras | El OOT se usó una sola vez (6.2 y 6.7) | Cumple |
| Leakage | Lista de variables prohibidas verificada por prueba automática | Cumple |
| Fairness | AIR por región, efectivo, edad y distancia; prueba de proxy | Cumple |
| Calibración vigente | Fecha del último ajuste y último semáforo (6.7 y 6.15) | Cumple |
| Aprobaciones | Acta del Comité que aprueba champion, apetito y umbrales | **Pendiente** |
| Pruebas automáticas | Suite en verde, cubre contrato de API, política y modelos | Cumple |
| Plan de remediación | Cada hallazgo con responsable y fecha comprometida | Cumple |

El único pendiente es el acta del Comité: es un acto de gobierno de la entidad, no un entregable técnico. Todo lo demás tiene evidencia en el repositorio.

## 9. Trazabilidad del requisito 6.14

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Ficha técnica / Model Card del champion y fichas resumidas de EAD y LGD | §6 · `models/model_card_scorecard_pd.md`, `ficha_ead.md`, `ficha_lgd.md` |
| Inventario de modelos, roles de aprobación, ciclo de vida y tres líneas de defensa | §3, §4 y §5 · `gobierno_inventario.csv`, `gobierno_ciclo_de_vida.csv` |
| Criterios de materialidad / clasificación y frecuencia de revisión | §2 · `gobierno_materialidad.csv` |
| Validación independiente simulada con 5+ findings (severidad, evidencia, impacto, recomendación, responsable) | §7 · `reports/independent_validation_report.md` · 10 hallazgos |
| Checklist mínimo para auditoría y evidencia de reproducibilidad | §8 · `gobierno_checklist_auditoria.csv` |
