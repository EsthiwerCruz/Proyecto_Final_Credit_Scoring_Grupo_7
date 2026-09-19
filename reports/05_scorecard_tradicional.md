# 6.5 · Scorecard tradicional PD

**Caso 15 · Caja Rural 360 — Microcrédito rural para independientes**

> **Evidencia:** `notebooks/03_scorecard_pd.ipynb`; código en `src/scorecard.py`; tablas en `reports/tables/` (prefijo `scorecard_`); figuras `fig19` a `fig21`; artefacto versionado en `models/scorecard_pd_v1.json`.

---

## 1. Resumen

- **Scorecard de tres características:** score de buró, DTI post-crédito y ahorro sobre monto solicitado. Coeficientes negativos, significativos y cercanos a −1, con VIF ≈ 1.01.
- **Escala:** 600 puntos equivalen a odds de 10:1 (buenos:malos) y cada **PDO = 20 puntos duplica las odds**. El score va de 543 a 653 con 73 valores distintos.
- **Desempeño:** Gini 0.440 y KS 0.334 en DEV; Gini 0.348 y KS 0.298 en VAL. La caída no es sobreajuste: el mismo scorecard da 0.487 / 0.366 / 0.464 por año en DEV, y el buró solo se mueve igual, así que 2024 se parece a 2022.
- **Selección con criterios fijados antes de mirar resultados (S1-S7).** La mora previa queda fuera porque se invierte en VAL; la sensibilidad confirma que incluirla subiría el Gini de DEV (+1.1 pts) y bajaría el de VAL (−1.3 pts).
- **El orden funciona, el nivel no:** en VAL la PD de desarrollo subestima 41% y el desvío crece en las bandas altas. La escala de puntos queda congelada y lo que se recalibra en 6.7 es la tabla score → PD, con un método que ajuste intercepto **y** pendiente.
- **Sin reject inference en el champion:** aun suponiendo que los rechazados incumplen el doble de lo que dice el modelo, el orden del score no cambia (Spearman 0.9996) y el Gini de VAL queda igual.

## 2. Parámetros del binning

La clasificación fina parte de 20 cuantiles (o de cada valor cuando hay pocos) y agrupa con reglas fijas: mínimo **5% de DEV y 15 defaults** por tramo, **monotonía** en la dirección de negocio esperada, máximo **6 tramos** y fusión de tramos contiguos con riesgo prácticamente igual (diferencia de log-odds < 0.05).

La única decisión abierta era si fusionar además los tramos contiguos sin diferencia estadísticamente significativa. Se resolvió con **validación temporal dentro de DEV** (tramos ajustados en 2021-2022, evaluados en 2023), como permite 6.2:

| Fusión por significancia | Tramos (buró / capacidad / ahorro) | Gini 2023 | Puntajes distintos |
|---|---|---|---|
| Sí, alfa 0.05 | 4 / 2 / **1** | 0.395 | 22 |
| Sí, alfa 0.10 o 0.20 | 4 / 3 / 2 | 0.422 | 47 |
| **No (elegida)** | **5 / 4 / 4** | **0.433** | **112** |

Con alfa 0.05 el ahorro desaparece como variable y el scorecard queda con 22 puntajes, insuficiente para definir un punto de corte (6.9) o analizar deciles (6.7). Sin esa fusión, el orden de los tramos se mantiene en 2023 (Spearman −1.0 en buró y capacidad, −0.8 en ahorro), que es la estabilidad que esa regla buscaba proteger y que los mínimos de tamaño ya garantizan.

## 3. Binning, WOE e IV: criterios de selección

**WOE = ln(%buenos / %malos)**, así que WOE alto es menos riesgo. El IV se acompaña de una **prueba de permutación** (200 repeticiones con el target permutado y el mismo binning): sin ese contraste el IV engaña, porque un binning que optimiza también produce IV > 0 sobre ruido.

| Criterio | Definición |
|---|---|
| S1 | IV ≥ 0.02 en DEV |
| S2 | El IV no es un artefacto del binning (permutación, p < 0.05) |
| S3 | Dirección del riesgo con sentido de negocio documentado |
| S4 | El tramo de más riesgo supera al de menos riesgo en 2021-2022 y en 2023 |
| S5 | PSI de tramos DEV→VAL y DEV→OOT < 0.10 (sin target) |
| S6 | No se invierte en VAL: el orden se mantiene y el IV medido en VAL es positivo |
| S7 | No está excluida por diseño (fairness) |

**Resultado** (`scorecard_seleccion_univariada.csv`):

| Variable | Tramos | IV DEV | p permutación | IV en VAL | Decisión |
|---|---|---|---|---|---|
| `bureau_score` | 6 | 0.494 | 0.005 | 0.399 | **Pasa** |
| `dti_post` | 4 | 0.090 | 0.005 | 0.049 | **Pasa** |
| `dti` | 4 | 0.089 | 0.005 | 0.011 | **Pasa** |
| `ahorro_sobre_monto` | 3 | 0.047 | 0.005 | 0.034 | **Pasa** |
| `monthly_debt_payment` | 4 | 0.028 | 0.025 | 0.026 | **Pasa** |
| `prior_delinquencies_24m` | 3 | 0.030 | 0.005 | **−0.008** | Fuera: S6 |
| `region` | 4 | 0.023 | 0.094 | 0.017 | Fuera: S2 y S7 |
| `savings_balance` | 4 | 0.021 | 0.075 | 0.003 | Fuera: S2 |
| Otras 14 candidatas | 1-5 | 0.000-0.013 | — | — | Fuera: S1 |

Tres lecturas que conviene poder defender:

- **El IV del buró (0.494) está cerca del umbral de 0.5 donde conviene sospechar de leakage.** Aquí se explica sin leakage: es un score de riesgo comprado al buró, medido en T0 y disponible antes de la decisión (verificado en 6.2). Su alto poder es el hallazgo 2 de 6.4, no un error de diseño.
- **La mora previa cae por S6.** Ordena en DEV (8.8% / 11.7% / 12.8%) pero en VAL el patrón se rompe (14.7% / 11.9% / 17.0%) y el IV medido en VAL con los WOE de DEV es negativo: los tramos aprendidos dejan de separar.
- **Las cinco variables excluidas por fairness** (edad, región, distancia, dependientes, efectivo) tienen IV entre 0.002 y 0.023 y ninguna pasa S1-S2: **excluirlas no cuesta poder predictivo**. Esa es la respuesta a la pregunta del caso sobre qué variables no deberían usarse aunque mejoren una métrica.

**Faltantes con WOE neutral, por decisión.** Si se usara el WOE observado en DEV, la solicitud sin score de buró recibiría +0.74 de WOE, unos **22 puntos de regalo**, sostenidos por 6 defaults en 126 créditos y concentrados en 2021-2022 (6.3). Con WOE neutral queda en el promedio de la cartera y la política la manda a revisión con re-consulta del buró.

| Variable | Créditos con faltante (DEV) | Default | WOE observado | WOE asignado |
|---|---|---|---|---|
| `bureau_score` | 126 | 4.8% | +0.74 | 0.00 |
| `dti_post` | 85 | 8.2% | +0.17 | 0.00 |
| `ahorro_sobre_monto` | 255 | 9.0% | +0.12 | 0.00 |

## 4. Selección multivariada

Redundancia sobre los WOE (tope Spearman 0.60): `dti` y `dti_post` correlacionan 0.72 y no pueden convivir; `monthly_debt_payment` correlaciona 0.50-0.64 con ambas. El buró y el ahorro son independientes del resto.

Como 6.3 dejó abierta la elección entre `dti` y `dti_post`, se compararon **dos especificaciones fijadas de antemano**, con la regla —también fijada antes— de quedarse con A salvo que B fuera significativamente mejor en VAL:

| Especificación | Variables | Gini DEV | Gini VAL | KS VAL |
|---|---|---|---|---|
| **A · `dti_post`** | buró, `dti_post`, `ahorro_sobre_monto` | 0.440 | **0.348** | 0.298 |
| B · `dti` | buró, `dti`, `ahorro_sobre_monto` | 0.447 | 0.316 | 0.281 |

Diferencia de AUC en VAL (A − B): **+0.016, con IC 95% de +0.003 a +0.030**. Gana A, que además es la que reacciona a una contraoferta de monto o plazo y coincide con la regla de capacidad de la política.

En el stepwise, `monthly_debt_payment` no entra (p = 0.52 sobre A): su señal ya está en la capacidad de pago.

**Sensibilidad de lo que quedó fuera.** Si `prior_delinquencies_24m` hubiera entrado, el Gini de DEV subiría a 0.451 (+1.1 pts) y el de VAL bajaría a 0.335 (−1.3 pts). Es el caso de manual de una variable que luce bien en desarrollo y falla después: el criterio S6 la dejó fuera antes de ver ese resultado.

## 5. Scorecard final

| Característica | Coeficiente | Error estándar | p | VIF |
|---|---|---|---|---|
| Intercepto | −2.2168 | 0.0619 | < 0.001 | — |
| `bureau_score` (WOE) | −1.0373 | 0.0877 | < 0.001 | 1.00 |
| `dti_post` (WOE) | −1.0345 | 0.1895 | < 0.001 | 1.01 |
| `ahorro_sobre_monto` (WOE) | −0.8880 | 0.2709 | 0.001 | 1.01 |

Con codificación WOE, coeficientes cercanos a −1 indican que el efecto multivariado casi coincide con el univariado: las tres características aportan información propia y no se estorban.

**Tabla de puntos** (`scorecard_puntos.csv`):

| Característica | Tramo | WOE | Puntos |
|---|---|---|---|
| Score de buró | ≤ 596 | −1.014 | 169 |
| | 596-642 | −0.347 | 189 |
| | 642-670 | 0.241 | 206 |
| | 670-698 | 0.309 | 208 |
| | 698-732 | 0.434 | 212 |
| | > 732 | 1.316 | 239 |
| | Sin dato | 0.000 | 199 |
| DTI post-crédito | ≤ 41.3% | 0.279 | 207 |
| | 41.3%-49.3% | 0.071 | 201 |
| | 49.3%-59.3% | −0.179 | 194 |
| | > 59.3% | −0.466 | 185 |
| | Sin dato | 0.000 | 199 |
| Ahorro / monto solicitado | ≤ 0.126 | −0.400 | 189 |
| | 0.126-0.599 | −0.096 | 197 |
| | > 0.599 | 0.293 | 207 |
| | Sin dato | 0.000 | 199 |

**Escala.** Base Score 600 = Base Odds 10:1 (buenos:malos), PDO 20 → factor 28.854 y offset 533.561. La elección se justifica con el dato: las odds promedio de DEV son 8.8:1, que en esta escala equivalen a 596 puntos, así que un solicitante típico queda cerca de 600 y la lectura es intuitiva para negocio. Redondear los puntos no cuesta discriminación (Spearman 0.9997 contra el score exacto; mismo Gini).

El artefacto `models/scorecard_pd_v1.json` guarda tramos, WOE, coeficientes y escala. Una prueba de `tests/test_scorecard.py` verifica que ese archivo reproduce exactamente el scorecard que ajusta el código, de modo que no puedan desincronizarse.

## 6. Desempeño, bandas y estabilidad

| Métrica | DEV | VAL |
|---|---|---|
| Gini del scorecard | 0.440 | 0.348 |
| KS | 0.334 | 0.298 |
| Gini del buró solo | 0.374 | 0.318 |
| Gini de una logística continua con las mismas 3 variables | 0.412 | 0.365 |

**Gini por año:** 0.487 (2021), 0.366 (2022), 0.464 (2023), 0.348 (2024). El buró solo se mueve igual (0.392 / 0.333 / 0.395 / 0.318). La caída de DEV a VAL es variación de cosecha, no deterioro del modelo: 2024 se parece a 2022, que está dentro del propio desarrollo.

Frente al buró solo, el scorecard agrega 6.6 puntos de Gini en DEV y 3.1 en VAL, aunque en un solo año esa diferencia no alcanza significancia (IC de −0.007 a +0.040). Frente a la logística continua, gana en DEV y pierde por poco en VAL: la diferencia está dentro del ruido y se prefiere el scorecard por interpretabilidad, tratamiento explícito de faltantes y razones de decisión.

**Bandas de score** (cada banda de 20 puntos es una duplicación de odds):

| Banda | % créditos DEV | Default DEV | Default VAL |
|---|---|---|---|
| ≤ 560 | 3.8% | 27.9% | 27.3% |
| 560-580 | 14.0% | 23.8% | 25.6% |
| 580-600 | 25.6% | 11.1% | 20.3% |
| 600-620 | 33.1% | 7.0% | 8.9% |
| 620-640 | 14.3% | 3.3% | 7.7% |
| > 640 | 9.3% | 1.9% | 4.6% |

El orden se mantiene banda a banda en las dos muestras. El **PSI del score es 0.005 hacia VAL y 0.008 hacia OOT**: la población que llega es la misma, así que lo que cambió es el riesgo, no la mezcla.

## 7. Calibración: la PD de desarrollo no es la PD de producción

| Banda | PD de desarrollo | Default observado VAL | Observado / predicho |
|---|---|---|---|
| ≤ 560 | 33.7% | 27.3% | 0.81 |
| 560-580 | 21.4% | 25.6% | 1.20 |
| 580-600 | 12.2% | 20.3% | 1.66 |
| 600-620 | 6.5% | 8.9% | 1.37 |
| 620-640 | 3.7% | 7.7% | 2.06 |
| > 640 | 2.0% | 4.6% | 2.38 |
| **Total** | **9.9%** | **14.0%** | **1.41** |

En DEV la calibración es correcta por construcción (observado/predicho entre 0.83 y 1.13). En VAL el modelo **subestima 41%** y el desvío crece en las bandas altas. Tres consecuencias:

1. La **escala de puntos queda congelada**; lo que se recalibra es la tabla score → PD, para que el punto de corte y las bandas no se muevan cada vez que cambia el nivel de riesgo.
2. Como el desvío no es un corrimiento paralelo, la recalibración de 6.7 debe ajustar **intercepto y pendiente** (Platt) y compararse contra isotónica.
3. El motor de decisión y el Expected Loss deben usar la **PD recalibrada**: con la PD de desarrollo, la pérdida esperada quedaría subestimada en aproximadamente el mismo 40%.

## 8. Sesgo de selección: sensibilidad con reject inference

El scorecard se ajusta con aprobados (known good/bad). 6.2 mostró que el filtro histórico fue débil (AUC de la aprobación 0.62, con aprobaciones en todo el rango de score), así que el sesgo esperado es moderado. Se midió con **aumentación difusa**: cada rechazado de 2021-2023 entra como bueno y como malo con pesos (1 − p, p), con p igual a la PD del scorecard multiplicada por un factor de castigo.

| Escenario | Coeficiente buró | Spearman del score vs. A | Gini VAL |
|---|---|---|---|
| Sin reject inference (scorecard A) | −1.037 | 1.000 | 0.348 |
| Rechazados 1.0× la PD del modelo | −1.036 | 1.000 | 0.348 |
| Rechazados 1.5× | −1.097 | 0.9997 | 0.350 |
| Rechazados 2.0× | −1.154 | 0.9996 | 0.350 |

Los rechazados tienen una PD media de 12.6% frente a 10.2% de los aprobados, así que la política histórica sí filtraba algo. Aun con el supuesto más duro, **el orden del score no cambia**. Por eso no se aplica reject inference al champion: con este dato el método es circular (parte de la PD del propio modelo) y no agrega información. Se documenta como sensibilidad y el control real es de monitoreo: seguir el default de los aprobados en las bandas bajas, donde la nueva política aprobará solicitudes que antes se rechazaban.

## 9. Razones de decisión

Las razones son las características que más puntos restan frente a su mejor tramo, y son lo que devuelve la API en `reason_codes` (6.13 y 6.16 del enunciado). Cuando el dato falta, el mensaje lo distingue: no es lo mismo "score de buró bajo" que "score de buró no disponible (re-consultar)".

| Caso (VAL) | Score | PD de desarrollo | Razones |
|---|---|---|---|
| Mejor score | 653 | 1.6% | Ninguna (máximo en las tres características) |
| Score mediano | 604 | 8.0% | Score de buró bajo · Carga de deuda post-crédito alta |
| Peor score | 543 | 41.9% | Score de buró bajo · Carga de deuda post-crédito alta · Ahorro bajo frente al monto |
| Sin score de buró | 591 | 12.0% | Score de buró no disponible · Carga de deuda post-crédito alta |

## 10. Limitaciones y qué sigue

- **Un solo scorecard para todos los canales y regiones.** Lo respalda 6.4: el buró ordena igual en los cuatro canales (AUC 0.66-0.71), así que segmentar agregaría complejidad sin evidencia.
- **Tres características son pocas, pero es lo que el dato sostiene.** El ejercicio con la mora previa muestra el costo de agregar variables sin estabilidad: sube el Gini de desarrollo y baja el de validación.
- **La PD del scorecard es de desarrollo** y no debe usarse sin recalibrar (§7).
- **No se aplicó reject inference al champion** (§8), y la nueva política deberá monitorear a los aprobados de bandas bajas.
- **Pendiente para 6.6 y 6.7:** Random Forest, XGBoost y LightGBM como challengers con la misma partición, selección de champion por criterio integral (no solo AUC), recalibración y métricas completas sobre OOT, que en 6.5 no se tocó.

## 11. Trazabilidad del requisito 6.5

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Binning + WOE + IV + regresión logística | §2 a §5 · `src/scorecard.py` · notebook §1-§4 |
| Monotonicidad | Regla del binning (§2) · prueba `test_binning_respeta_minimos_y_monotonia` |
| Bins pequeños | Mínimo 5% de la muestra y 15 defaults por tramo (§2) |
| Missing bins | §3 · `scorecard_faltantes_woe.csv` |
| Estabilidad | §3 (S4-S6, PSI por tramo) y §6 (PSI del score, Gini por año) |
| Justificación de selección y eliminación de variables | §3 (S1-S7) y §4 (stepwise, especificaciones, sensibilidad) |
| Scorecard final documentado | §5 · `scorecard_puntos.csv` · `models/scorecard_pd_v1.json` |
| Escala con Base Score, Base Odds y PDO | §5 · 600 puntos = odds 10:1, PDO 20 |
