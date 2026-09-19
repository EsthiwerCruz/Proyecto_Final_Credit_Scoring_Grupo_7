# 6.9 · Cut-off, reglas, Decision Engine y rentabilidad

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/07_decision_engine.ipynb`; código en `src/decision.py`; tablas `decision_*.csv`; figura `fig27`; artefacto `models/politica_decision_v1.json`.

---

## 1. Resumen

- La decisión combina **PD calibrada** (6.7), **capacidad de pago**, **reglas duras** de política (6.1) y el **apetito de riesgo**, y devuelve tres salidas: APPROVE, REVIEW y REJECT, con motivo, monto recomendado y tasa recomendada.
- **Política recomendada:** aprobación automática con PD calibrada ≤ 18%, rechazo sobre 20%, contraoferta automática de monto hasta un DTI post-crédito de 45%, y revisión manual para cuatro reglas verificables.
- En 2024 esa política aprueba automáticamente 53.3%, manda a revisión 23.2% y rechaza 23.5%. La cartera final esperada tiene **10.7% de default y 2.9% de pérdida esperada sobre monto**, dentro de los límites del apetito.
- En **2025 (OOT)**, que nunca se usó para construirla, aprueba 64.6% con 9.3% de default esperado frente a la política histórica que aprobó 81.6% con 13.4%: **17 puntos menos de aprobación a cambio de 4.1 puntos menos de default**.
- El **swap-out tenía 19.4% de default observado** contra 9.8% de los que se mantienen aprobados: el modelo saca justo la parte de la cartera que explicaba la pérdida.
- **El conflicto crecimiento-riesgo es real y se nombra**: no existe un corte que cumpla a la vez el objetivo de aprobación (≥ 70%) y el límite de default (≤ 11%). Aplica la regla de precedencia del apetito: prevalece el límite de riesgo.

## 2. Árbol de decisión

El orden importa, porque una solicitud puede caer en más de una regla:

1. **REVIEW cuando falta información**: sin score de buró (re-consultar) o sin ingreso declarado (verificar en campo). Van **antes** del rechazo a propósito: si el insumo principal del modelo está imputado, la PD no es confiable y no corresponde rechazar en automático. Es lo que fija la política de 6.1 y lo que sostiene el argumento de fairness de 6.8.
2. **REJECT** si la PD calibrada ≥ 20%: aquí el modelo tiene toda su información y el riesgo está fuera del apetito aun con contraoferta.
3. **REVIEW por verificación**, cuando el dato existe pero hay que sustentarlo: monto > S/ 20,000 (6.4 mostró que ese tramo es errático y concentra exposición) e ingreso en efectivo > 80% con ticket > S/ 10,000 (verificar, no penalizar).
4. **Contraoferta automática de monto**: si el monto pedido excede la capacidad, el motor calcula el máximo que deja el DTI post-crédito en 45% y **recalcula la PD con ese monto** (el scorecard reacciona al monto a través del DTI post-crédito). Exceder el DTI **no** manda a analista: dispara una contraoferta.
5. Si ni con la contraoferta hay monto comercial (menos de S/ 1,000): **REVIEW** cuando el riesgo es bajo (evaluar plazo mayor o consolidación) y **REJECT** cuando además la PD está fuera del tramo automático. A quien va a analista por capacidad se le calcula el techo del **60% de DTI post-crédito**, que es hasta donde la política de 6.1 permite llegar con validación: el analista recibe un monto concreto, no un "no".
6. **REVIEW** en la zona gris (PD entre 18% y 20%); **APPROVE** en el resto.

**Trazabilidad con los disparadores de revisión de 6.1 §8.** Los cuatro primeros se implementan tal cual. El quinto, distancia mayor a 50 km, **no se implementa**: 6.4 mostró que ese segmento no tiene peor default ni peor LGD y que el costo de recuperación no crece con la distancia (Spearman 0.03, p = 0.48). Mantenerlo habría gastado capacidad de análisis en un grupo sin evidencia de riesgo y habría penalizado justo a la población que el caso quiere incluir.

## 3. Elección del cut-off

Tres restricciones, en este orden:

1. **Default de la cartera final ≤ 11%** y **pérdida esperada ≤ 3%** (límites de riesgo del apetito, 6.1).
2. **Revisión manual ≤ 20%** de las solicitudes, que es la capacidad declarada de los analistas.
3. Maximizar aprobación y resultado dentro de lo anterior.

Con la zona gris fijada en dos puntos de PD (rechazo = aprobación + 2 pp), la curva sobre las solicitudes de 2024 queda así:

| PD de aprobación | Aprobación automática | Revisión | Rechazo | Aprobación final | Default de la cartera | Pérdida esperada |
|---|---|---|---|---|---|---|
| 12% | 37.0% | 19.1% | 43.9% | 48.5% | 8.0% | 2.2% |
| 15% | 46.3% | 22.4% | 31.3% | 59.7% | 9.5% | 2.6% |
| **18% (elegida)** | **53.3%** | **23.2%** | **23.5%** | **67.2%** | **10.7%** | **2.9%** |
| 20% | 55.7% | 25.9% | 18.4% | 71.2% | 11.7% | 3.1% |
| 24% | 61.1% | 29.2% | 9.8% | 78.6% | 13.0% | 3.5% |

Subir a 20% rompe los dos límites de riesgo (default 11.7% y pérdida 3.1%) y además exige más revisión; bajar a 15% cuesta 7.5 puntos de aprobación final para ganar 1.2 puntos de default. La zona gris quedó estrecha a propósito (18% a 20%): con la capacidad de 20%, casi todo el cupo lo consumen las reglas duras, que son las que un analista **puede efectivamente resolver**. Ampliar la zona gris sin ampliar la capacidad solo generaría una cola.

*La evaluación se hace sobre todas las solicitudes (TTD), no solo las históricamente aprobadas: donde hay resultado observado se usa el observado y donde no (rechazados históricos), la PD calibrada. La aprobación final supone que el analista aprueba el 60% de las revisiones, supuesto explícito en `config.REVIEW_APPROVAL_RATE`.*

## 4. Resultados de la política en 2024

| Decisión | Motivo | % de solicitudes |
|---|---|---|
| APPROVE | Riesgo y capacidad dentro del apetito | 41.0% |
| APPROVE | Aprobado con contraoferta de monto | 12.2% |
| REVIEW | Capacidad de pago insuficiente: evaluar plazo o consolidación | 10.4% |
| REVIEW | Sin score de buró | 3.2% |
| REVIEW | Monto > S/ 20,000 | 2.7% |
| REVIEW | PD entre 18% y 20% | 2.5% |
| REVIEW | Efectivo alto con ticket alto | 2.4% |
| REVIEW | Sin ingreso declarado | 2.1% |
| REJECT | PD calibrada ≥ 20% | 23.4% |
| REJECT | Capacidad insuficiente y PD fuera del tramo | 0.1% |

Poco más de la mitad se resuelve sola, 23.5% se rechaza por riesgo y 23.2% va a analista **por reglas verificables, no por dudas del modelo** (la zona gris de PD explica apenas 2.5 puntos de esa revisión). El motor contraoferta monto en el 12% de los casos y ofrece, en promedio, **90% del monto pedido** entre los aprobados: es el mecanismo que permite decir que sí con menos exposición en lugar de decir que no.

## 5. Swap-in / swap-out contra la política histórica (2024)

| Grupo | Solicitudes | Default observado |
|---|---|---|
| Se mantienen aprobados | 46.9% | 9.8% |
| **Swap-out: salen** | 35.9% | **19.4%** |
| Swap-in: entran | 6.3% | — (antes rechazados) |
| Se mantienen fuera | 10.8% | — |

El swap-out duplica el default de los que se mantienen: el recorte no es al azar. En paralelo entra un 6.3% de solicitudes que la política histórica rechazaba y que ahora califican, en línea con el objetivo de inclusión del caso.

## 6. Pricing por riesgo y asignación de monto

    tasa = costo de fondos (6%) + gasto operativo (5%) + prima de riesgo + margen objetivo (5%)
    prima de riesgo = (PD × EAD/monto 0.42 × LGD 0.62) / (factor de saldo 0.55 × plazo en años)

con piso de 18% y techo de 60%. El **monto** se asigna por capacidad de pago, no por score: el máximo que deja el DTI post-crédito en 45%.

| Banda de PD | % de solicitudes | PD media | Tasa recomendada | Tasa histórica | Default observado |
|---|---|---|---|---|---|
| ≤ 5% | 8.4% | 4.5% | 18.2% | 25.4% | 4.6% |
| 5%-10% | 23.7% | 8.1% | 19.2% | 26.9% | 7.8% |
| 10%-18% | 40.6% | 13.6% | 21.3% | 28.8% | 13.3% |
| 18%-20% | 3.0% | 18.9% | 22.9% | 32.1% | 25.8% |
| > 20% | 24.3% | — | rechazo | 33.5%-36.4% | 23.5%-28.0% |

Dos consecuencias que conviene poner sobre la mesa:

- El pricing por riesgo va de 18.2% a 22.9% en las bandas que se aprueban: **la tasa propuesta es más barata en todas las bandas** y aun así cubre fondeo, gasto operativo, pérdida esperada y el margen objetivo. El margen sobre monto de la cartera aprobada cae de 22.0% (tasa histórica) a 10.3% (tasa propuesta) a lo largo de la vida del crédito.
- **La fórmula fija el piso, no el precio.** Subir el margen objetivo es una decisión comercial explícita del Comité. Lo que aporta el modelo es que la diferencia de tasa entre bandas queda **justificada por riesgo medido** y no por criterio del asesor: la banda más riesgosa que se aprueba paga 4.8 puntos más que la más sana.

## 7. Risk Appetite: cumplimiento y conflicto

| Métrica | Tipo | Verde | Política | ¿Cumple? |
|---|---|---|---|---|
| Aprobación final (TTD) | Objetivo de negocio | ≥ 70% | 67.2% | **No** |
| Default 12m de la cartera | Límite de riesgo | ≤ 11% | 10.7% | Sí |
| Pérdida esperada / monto | Límite de riesgo | ≤ 3% | 2.9% | Sí |
| Revisión manual | Restricción operativa | ≤ 20% | 23.2% | **No: excede algo más de 3 puntos (45 casos al año)** |

Con el nivel de riesgo de 2024-2025 **no existe** un corte que cumpla a la vez el objetivo de aprobación y el límite de default. Aplica la **regla de precedencia** escrita en el apetito (6.1): prevalece el límite de riesgo y no se relaja el corte para sostener la aprobación.

La cola de revisión queda algo más de 3 puntos por encima de la capacidad (45 casos al año en 2024). Se resuelve priorizando por valor esperado: primero los casos donde la verificación puede cambiar la decisión y el ticket es material. La alternativa con zona gris ancha (18%-25%) sube la aprobación final a 73.4%, pero lleva el default a 12.1% y la pérdida a 3.3% —rompe los dos límites— y exige 33.6% de revisión manual, 13 puntos por encima de la capacidad. No se recomienda; queda cuantificada para que el Comité decida con números si prefiere revisar el apetito o invertir en capacidad de verificación.

## 8. Confirmación en OOT 2025

| | Aprobación | Default | Revisión | Rechazo |
|---|---|---|---|---|
| Política histórica 2025 | 81.6% | 13.4% | — | 18.4% |
| **Política propuesta 2025** | **64.6%** | **9.3%** | 23.0% | 26.2% |
| Política propuesta 2024 | 67.2% | 10.7% | 23.2% | 23.5% |

En la cosecha que nunca se usó para construirla, la política mantiene la mezcla de decisiones y mejora el riesgo: pérdida esperada de 2.2% y resultado de 7.8% sobre monto.

## 9. Recomendación final

1. **Adoptar la política**: aprobación automática con PD calibrada ≤ 18%, rechazo sobre 20%, contraoferta automática de monto al 45% de DTI post-crédito y revisión manual para las cuatro reglas duras.
2. **Pricing por riesgo** con la fórmula de §6, piso 18% y techo 60%, revisando el margen objetivo con el Comité.
3. **Aceptar 65%-67% de aprobación** en el escenario actual, por precedencia del límite de riesgo. Si el negocio quiere crecer más, hay dos caminos cuantificados: ampliar la capacidad de verificación (la alternativa de §7 agrega 6.2 puntos de aprobación, aunque rompe los límites de riesgo) o revisar formalmente el apetito de default.
4. **Revisar el corte cuando se recalibre la PD** (6.7): los umbrales están en la escala de PD calibrada, así que se mantienen mientras la calibración esté vigente.
5. **Monitorear**: aprobación y default por cosecha, mezcla de decisiones, cola de revisión contra la capacidad de 20%, AIR por región y por ingreso en efectivo (6.8), y la brecha entre PD predicha y default observado como disparador de recalibración.

## 10. Limitaciones

- **EAD y LGD vienen de 6.10 y 6.11**: factor de exposición 0.415 y LGD contable 0.616, estimados con los defaults de DEV. Allí se muestra que ningún modelo le gana al baseline y que usar la **LGD económica** (descontada) subiría la pérdida esperada entre 6% y 15%; esa decisión de base se toma en 6.12, junto con el restateo del umbral del apetito.
- **La aprobación final depende de un supuesto**: que el analista aprueba el 60% de las revisiones. Con 40% la aprobación final baja a 62.6% y con 80% sube a 71.9%.
- **Los rechazados históricos entran con su PD, no con un resultado observado**: es el mismo supuesto de parceling de 6.1, razonable porque el filtro histórico fue débil, pero optimista si hubiera información que el modelo no ve.
- El resultado económico usa una estructura de costos simplificada (fondeo, gasto operativo y factor de saldo constantes), suficiente para comparar cortes pero no para presupuestar.

## 11. Trazabilidad del requisito 6.9

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Política que combina score/PD, capacidad de pago, reglas duras, apetito y criterios del producto | §2 y §4 · `src/decision.py` |
| Curva de trade-off con approval rate, bad rate, Expected Loss y métrica económica | §3 · `decision_curva_tradeoff.csv` · `fig27` |
| Tres salidas: APPROVE, REVIEW y REJECT | §2 y §4 · `decision_detalle_2024.csv` |
| Pricing por riesgo y asignación de monto, con fórmula, supuestos y restricciones | §6 · `decision_pricing_bandas.csv` |
| Recomendar una política final, no solo escenarios | §9 · artefacto `models/politica_decision_v1.json` |
