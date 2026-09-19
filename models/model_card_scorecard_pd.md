# Model Card · Scorecard PD — Caja Rural 360

*Generada automáticamente por `governance.build_model_card` el 2026-09-19. No editar a mano: se regenera con el notebook 11.*

## 1. Identificación

| Campo | Valor |
|---|---|
| Nombre | Scorecard PD · microcrédito rural |
| Versión | 1.0 · artefacto `scorecard_pd_v1.json` |
| Hash SHA-256 | `1516e158feace528703e84c79d2d8250…` |
| Estado | champion |
| Dueño | Equipo de Credit Risk Analytics |
| Entrenado con | DEV 2021-2023 |
| Materialidad | Tier 1 · alta (15 de 18 puntos) · Validación independiente anual, monitoreo trimestral y reporte al Comité |

## 2. Propósito y uso

**Para qué es.** Estimar la probabilidad de que un microcrédito rural alcance 90 días de mora dentro de los 12 meses siguientes al desembolso, y alimentar la decisión automática de originación (APPROVE / REVIEW / REJECT), el monto recomendado y el pricing por riesgo.

**Para qué NO es.** No estima recuperación ni severidad (eso es EAD y LGD), no decide cobranza ni gestión de cartera vigente, no sirve para carteras distintas del microcrédito rural, y **no debe usarse sin el calibrador vigente**: la PD del scorecard es de desarrollo.

**Quién lo consume.** El servicio de scoring (`api/main.py`) en la originación web, app, agencia y alianza, y el motor de decisión de 6.9.

## 3. Datos

| Aspecto | Detalle |
|---|---|
| Población | Solicitudes aprobadas con performance observable (`outcome_available_flag = 1`) |
| Target | `default_12m_flag`: 90+ días de mora dentro de 12 meses de `observation_date` |
| Muestras | DEV 2021-2023 (3,443 créditos, 351 defaults) · VAL 2024 · OOT 2025 |
| Variables | `bureau_score`, `dti_post` (DTI post-crédito), `ahorro_sobre_monto` |
| Excluidas por diseño | Edad, región, distancia, dependientes e ingreso en efectivo (fairness, 6.5) |
| Excluidas por leakage | Campos post-decisión y post-default; tasa ofrecida por endógena (6.2) |
| Tratamiento de faltantes | Imputación con la mediana de DEV; en el scorecard, WOE neutral |

## 4. Metodología

Binning supervisado con mínimos de 5% de la muestra y 15 defaults por tramo, monotonía en la dirección de negocio, WOE e IV, selección con siete criterios pre-registrados (S1 a S7) y regresión logística sobre los WOE. Escala: **600 puntos = odds 10:1, PDO 20**. La PD de producción es `Platt(PD del scorecard)` con intercepto -0.080 y pendiente 0.758, ajustado en VAL.

**Tabla de puntos** (resumen; completa en `reports/tables/scorecard_puntos.csv`):

| variable           |   min |   max |
|:-------------------|------:|------:|
| ahorro_sobre_monto |   189 |   207 |
| bureau_score       |   169 |   239 |
| dti_post           |   185 |   207 |

## 5. Desempeño

| Muestra | Gini | KS | Brier | Observado/predicho (antes de calibrar) |
|---|---|---|---|---|
| DEV | 0.440 | 0.331 | 0.086 | 0.999 |
| VAL | 0.348 | 0.298 | 0.117 | 1.413 |
| OOT | 0.424 | 0.338 | 0.110 | 1.312 |

Rango del Gini entre cosechas: 0.35 a 0.49. Una caída dentro de esa banda **no** es deterioro.

## 6. Fairness

Ninguna variable sensible entra al modelo y los insumos no permiten reconstruirlas (AUC 0.50 para región; R² ≈ 0 para efectivo, distancia, edad y dependientes). El AIR más bajo de la política es 0.74, en el quintil de mayor ingreso en efectivo, que se atiende con verificación y no con rechazo (hallazgo V-04).

## 7. Limitaciones

- La PD es de desarrollo: **requiere calibrador vigente**.
- Tres características son pocas, pero es lo que la evidencia sostiene: agregar variables sin señal mejora DEV y empeora VAL.
- Un solo scorecard para todos los canales y regiones (justificado en 6.4).
- Datos sintéticos: los parámetros no son trasladables a cartera real sin revalidar.

## 8. Monitoreo y disparadores

Semáforos y acciones en 6.15. Disparan recalibración: observado/predicho fuera de [0.85, 1.15] dos meses seguidos, o pérdida esperada de la cosecha sobre 3.34%. Dispara revisión de reentrenamiento: Gini bajo 0.30 o PSI del score sobre 0.10.

## 9. Gobierno

| Evento | Quién aprueba |
|---|---|
| Uso del modelo y umbrales de decisión | Comité de Riesgos |
| Promoción de challenger a champion | Comité de Riesgos, con validación independiente previa |
| Recalibración dentro de umbrales | Jefatura de Riesgos (informa al Comité) |
| Rollback | Jefatura de Riesgos, registrado en el Model Registry |

## 10. Reproducibilidad

Semilla 42, versiones fijadas en `requirements.txt`, artefacto versionado con hash en `models/registry.json`. `python run_all.py` reejecuta todo el proyecto y regenera este documento.
