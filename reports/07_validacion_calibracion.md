# 6.7 · Validación y calibración

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/05_validacion_calibracion.ipynb`; código en `src/evaluation.py`; tablas `validacion_*.csv`; figuras `fig23` y `fig24`; artefacto `models/calibrador_platt_v1.json`.

---

## 1. Resumen

- **Aquí se abre el OOT, una sola vez.** El modelo y su especificación quedaron congelados en 6.5 y 6.6 sin mirar 2025.
- El champion **ordena de forma estable**: Gini 0.440 en DEV, 0.348 en VAL y **0.424 en OOT**; KS 0.33, 0.30 y 0.34. La caída en VAL no era deterioro sino variación de cosecha, y 2025 lo confirma.
- El champion **no está calibrado**: subestima el default 41% en VAL y 31% en OOT, y el desvío no es un corrimiento paralelo (pendiente de calibración 0.76 en VAL).
- Se adopta **Platt** (intercepto y pendiente) ajustado en VAL: corrige el nivel sin tocar el orden ni el Gini. La isotónica mejora algo el error de calibración pero cuesta 1.8 puntos de Gini en OOT.
- El **PSI del score es 0.005 hacia VAL y 0.008 hacia OOT**: la población que llega es la misma; lo que cambió es el riesgo a igual perfil.
- El challenger ordenó algo mejor en OOT (+0.022 de AUC) pero **el intervalo incluye el cero**: el champion se mantiene y el challenger queda en seguimiento formal.

## 2. Discriminación y clasificación en las tres muestras

| Modelo | Muestra | AUC | Gini | KS | Brier | O/E | Pendiente de calibración |
|---|---|---|---|---|---|---|---|
| Champion · scorecard | DEV | 0.720 | 0.440 | 0.331 | 0.086 | 1.00 | 1.00 |
| | VAL | 0.674 | 0.348 | 0.298 | 0.117 | 1.41 | 0.76 |
| | **OOT** | **0.712** | **0.424** | **0.338** | 0.110 | 1.31 | 0.93 |
| Challenger · LightGBM monótono | DEV | 0.810 | 0.620 | 0.462 | 0.078 | 0.99 | — |
| | VAL | 0.655 | 0.309 | 0.250 | 0.119 | 1.44 | — |
| | OOT | 0.734 | 0.469 | 0.356 | 0.108 | 1.33 | — |

**Punto de operación.** Precision, recall, F1 y matriz de confusión necesitan un umbral. Se reportan dos:

- **Provisional (70% de aprobación en VAL, el objetivo del apetito):** en OOT, precisión 24% y recall 64%.
- **De política (PD calibrada de 18%, el corte de 6.9):** en OOT, precisión 25.9%, recall 50.3%, F1 0.342 y exactitud 74.1%, con 80 defaults marcados de 159 y 229 buenos marcados de 1,030.

Con una tasa base de 13%, **ningún corte convierte una cartera de microcrédito en una lista limpia**: por eso la decisión final no se juega en el F1 sino en el trade-off económico de 6.9.

## 3. Deciles, lift y ganancias (OOT 2025)

| Decil (1 = más riesgoso) | Créditos | Default | Lift | Captura acumulada de defaults |
|---|---|---|---|---|
| D1 | 119 | 27.7% | 2.07 | 20.8% |
| D2 | 119 | 26.9% | 2.01 | 40.9% |
| D3 | 119 | 20.2% | 1.51 | 56.0% |
| D4-D7 | 475 | 6.7%-15.1% | 0.50-1.13 | 90.6% |
| D10 | 119 | 2.5% | 0.19 | 100% |

Los tres deciles más riesgosos concentran el **56% de los defaults con el 30% de la cartera** (lift acumulado 1.7) y el decil más sano incumple 2.5% frente a 13.4% de la media. El KS acumulado llega a 0.32 alrededor del 40% de la población, que es justo la zona donde 6.9 ubica el rechazo.

## 4. Calibración: diagnóstico

| Muestra | PD media predicha | Default observado | O/E | Intercepto | Pendiente | ECE |
|---|---|---|---|---|---|---|
| DEV | 10.2% | 10.2% | 1.00 | 0.00 | 1.00 | 0.007 |
| VAL | 9.9% | 14.0% | 1.41 | −0.08 | 0.76 | 0.041 |
| OOT | 10.2% | 13.4% | 1.31 | +0.20 | 0.93 | 0.032 |

El modelo **ordena bien pero subestima el nivel**, tal como anticipó 6.4. La pendiente de 0.76 en VAL avisa que no es un corrimiento paralelo: corregir solo el intercepto dejaría mal calibradas las bandas altas, que son las que más pesan en la decisión de aprobar.

## 5. Recalibración: Platt vs. isotónica

Las dos se **ajustan en VAL** (la muestra que 6.2 reservó para calibrar) y se prueban en **OOT**, que es la única forma honesta de saber si la corrección generaliza.

| Método | Muestra | PD media | Observado | O/E | Brier | ECE | Gini |
|---|---|---|---|---|---|---|---|
| Sin recalibrar | OOT | 10.2% | 13.4% | 1.31 | 0.1099 | 0.032 | 0.424 |
| **Platt** | OOT | 14.3% | 13.4% | **0.94** | 0.1087 | 0.020 | **0.424** |
| Isotónica | OOT | 14.2% | 13.4% | 0.94 | 0.1087 | **0.015** | 0.406 |

**Decisión: Platt**, con intercepto −0.08 y pendiente 0.758. Razones:

1. Es una transformación **monótona estricta**: no cambia el orden, ni el Gini, ni las bandas de score que usa la política.
2. La isotónica gana 0.005 de ECE pero **sacrifica 1.8 puntos de Gini** en OOT porque escalona el score y crea empates dentro de los tramos.
3. Dos parámetros son auditables y explicables ante el Comité; una función escalonada ajustada con 161 defaults, no tanto.

Después de recalibrar, el modelo queda levemente **conservador** en OOT (predice 14.3% y se observa 13.4%), que es el lado correcto para provisionar. La PD de producción es `Platt(PD del scorecard)` y así queda registrada en `models/calibrador_platt_v1.json`.

## 6. Estabilidad

- **PSI del score:** 0.005 (DEV→VAL) y 0.008 (DEV→OOT). **PSI de la PD:** 0.011 y 0.010.
- **PSI de las tres características del scorecard:** ninguna supera 0.01 en VAL ni en OOT.
- **Gini por cosecha:** 0.49 (2021), 0.37 (2022), 0.46 (2023), 0.35 (2024), 0.42 (2025).

La conclusión operativa es doble: la mezcla de solicitantes no cambió, así que un PSI alto en el futuro sería una alerta genuina; y el rango natural del Gini entre cosechas es de unos 12 puntos, lo que fija el umbral realista del semáforo de monitoreo (6.15). Una caída de 12 puntos respecto de desarrollo **no** es, por sí sola, evidencia de deterioro: hay que compararla con esta banda histórica.

## 7. Champion vs. Challenger sobre el OOT

| Modelo | Gini OOT | KS OOT | Brier | O/E |
|---|---|---|---|---|
| Champion · scorecard | 0.424 | 0.338 | 0.110 | 1.31 |
| Challenger · LightGBM monótono | 0.469 | 0.356 | 0.108 | 1.33 |

Diferencia de AUC (challenger − champion): **+0.022, IC 95% de −0.002 a +0.044**. Incluye el cero.

Se reporta porque el gobierno del modelo lo necesita: el champion se eligió en 6.6 sin mirar el OOT y esta es la prueba independiente. **Recomendación:** mantener el scorecard como champion —interpretable, calibrable, de sub-milisegundo y con explicación exacta— y dejar el challenger en seguimiento. Si en dos cosechas seguidas la ventaja se sostiene con intervalo que excluya el cero, se promueve con el mismo veto de fairness, SHAP obligatorio y validación independiente.

## 8. Trazabilidad del requisito 6.7

| Requisito del enunciado | Dónde se cumple |
|---|---|
| AUC/ROC, Gini, KS, Precision, Recall, F1, matriz de confusión, Brier, Lift/Gains y deciles | §2 y §3 · `validacion_metricas.csv`, `validacion_deciles_oot.csv` · `fig23` |
| Performance en Development, Validation y OOT | §2 · las tres muestras en la misma tabla |
| Curva de calibración y PD predicha vs. default observado por bandas | §4 y §5 · `fig24` · `validacion_calibracion_diagnostico.csv` |
| Método de recalibración probado y justificado, con antes/después | §5 · Platt vs. isotónica, ajuste en VAL y prueba en OOT · `validacion_recalibracion.csv` |
| Estabilidad del score y de las variables con PSI | §6 · `validacion_estabilidad.csv` |
