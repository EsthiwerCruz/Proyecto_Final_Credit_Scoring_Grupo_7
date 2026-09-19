# 6.12 · Expected Loss, portafolio y stress testing

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/09_expected_loss_stress.ipynb`; código en `src/portfolio.py`; tablas `el_*.csv`; figuras `fig31` a `fig33`; **tablero** en `reports/dashboard_cartera.html`.

---

## 1. Resumen

- Se integran las tres piezas a nivel de cada solicitud: **PD calibrada** (6.7) × **factor de exposición 0.415** (6.10) × **LGD** (6.11), sobre la cosecha 2025 con la política de 6.9 aplicada.
- **Se adopta la LGD económica** (descontada a la tasa efectiva que cobraría la política, 20.2%): 0.686 en lugar de 0.616. Y se **restatea el umbral del apetito en la misma base**: 3.34% en verde y 3.89% en rojo.
- Cartera resultante: S/ 6.18 millones colocados, PD ponderada 10.4%, **pérdida esperada de S/ 185 mil, 2.99% sobre monto**, dentro del apetito restateado.
- Tres escenarios con shocks atados a lo observado. En **Severe** la pérdida esperada llega a 5.28% y la aprobación cae sola a 36.5%.
- **Hallazgo central: la política es un estabilizador automático.** Si la cartera se congelara, la pérdida esperada en Severe sería 6.80% en lugar de 5.28%: el corte expresado en PD calibrada absorbe 1.5 puntos del shock.
- El costo de riesgo total (pérdida esperada más capital al 99.9%) va de 6.9% del monto colocado en Base a 10.9% en Severe.

## 2. Base de la LGD y restateo del umbral

6.11 mostró que la LGD del archivo no descuenta. Aquí se toma la decisión pendiente:

| Concepto | Base contable | Base económica |
|---|---|---|
| LGD (DEV) | 0.616 | **0.686** |
| Factor de restateo | — | **1.113** |
| Umbral verde del apetito | 3.0% | **3.34%** |
| Umbral rojo del apetito | 3.5% | **3.89%** |

La tasa de descuento es **la tasa efectiva que cobraría la política propuesta (20.2%)**, no la histórica: se descuenta al rendimiento de los créditos que realmente se van a colocar.

El restateo no es un truco para pasar el semáforo, es la condición para que la comparación tenga sentido. De hecho, mirada en la base correcta, **la política histórica ya venía incumpliendo**: su pérdida realizada de 2024 (4.01% contable) equivale a 4.46% económico, muy por encima del rojo restateado.

| Cosecha | Pérdida realizada (contable) | En base económica |
|---|---|---|
| 2021 | 1.89% | 2.10% |
| 2022 | 2.34% | 2.60% |
| 2023 | 3.00% | 3.34% |
| 2024 | 4.01% | 4.46% |
| 2025 | 3.37% | 3.75% |

## 3. Expected Loss a nivel cliente y cartera

| Métrica | Cartera 2025 con la política propuesta |
|---|---|
| Solicitudes con colocación esperada | 1,022 (equivalen a 942 créditos completos, contando las revisiones al 60%) |
| Monto colocado | S/ 6,176,001 |
| Exposición esperada al default (EAD) | S/ 2,563,040 |
| PD ponderada por monto | 10.4% |
| LGD (económica) | 68.6% |
| **Pérdida esperada** | **S/ 184,657 · 2.99% del monto** |

*Nota de comparabilidad:* 6.9 reporta la pérdida esperada de la cosecha **2024 en base contable** (2.9%) y esta sección, la de la cosecha **2025 en base económica** (2.99%). Cambian el año y la base, así que no son cifras comparables entre sí; lo comparable es cada una contra su propio umbral.

**Concentración de la pérdida.** Por decil de PD de la cartera ya aprobada: el decil más riesgoso tiene 7.2% del monto y 12.5% de la pérdida esperada; los dos peores, 17.4% del monto y 28.1% de la pérdida. Es una concentración **moderada**, y eso es buena señal: la concentración fuerte que mostraba 6.4 (dos quintiles de buró con 65% de la pérdida) ya fue removida por el punto de corte. Lo que queda dentro es una cartera razonablemente homogénea.

## 4. Tablero de cartera por segmento

`reports/dashboard_cartera.html` es un tablero autocontenido (tablas y figuras embebidas, sin dependencias externas) que se regenera con cada corrida del notebook. Incluye exposición, PD, EAD, LGD, EL, participación, default observado, margen y resultado por segmento, más los escenarios y la concentración.

Lo que muestra, en resumen:

| Dimensión | Segmento | % del monto | EL / monto | Resultado / monto |
|---|---|---|---|---|
| Capacidad (DTI post) | ≤ 30% | 34.1% | 2.71% | **9.41%** |
| Capacidad (DTI post) | 30-45% | 39.6% | 2.90% | 6.38% |
| Capacidad (DTI post) | 45-60% | 18.6% | 3.34% | 5.01% |
| Capacidad (DTI post) | > 60% | 5.3% | 4.01% | **2.81%** |
| Banda de score | > 640 | 14.8% | 1.28% | **8.28%** |
| Banda de score | 600-620 | 45.4% | 3.09% | 7.36% |
| Banda de score | 580-600 | 22.8% | **4.63%** | 5.43% |
| Tramo de monto | > S/ 20,000 | 11.2% | 3.32% | 7.36% |
| Región | Norte / Sur | 20.1% / 13.9% | 3.04% / 2.93% | 7.52% / 6.70% |

Concentración (HHI del monto): entre 0.25 y 0.31 en score, región, canal, monto y capacidad; 0.48 en ingreso en efectivo, que refleja la composición del mercado objetivo y no una decisión de la política.

## 5. Escenarios de stress

Cada shock está atado a algo observado en la propia cartera. El shock de PD se aplica sobre las **odds** y no sobre la PD, para que el deterioro sea proporcional en toda la distribución, que es como se observó entre 2021 y 2024 (6.4: desplazamiento de nivel con pendiente estable).

| Escenario | Shock de PD | LGD | EAD/monto | Justificación |
|---|---|---|---|---|
| Base | odds × 1.00 | 0.686 | 0.415 | Nivel actual: PD calibrada con VAL, LGD económica de largo plazo |
| Adverse | odds × 1.44 | 0.695 | 0.453 | Dos años más de la tendencia observada (odds × 1.20 por año, 6.4), LGD de la peor cosecha y exposición del percentil 90 trimestral |
| Severe | odds × 2.00 | 0.745 | 0.486 | Odds × 2 (peor trimestre observado contra el mejor), recargo prudencial de 5 pp sobre la LGD de downturn y peor exposición trimestral |

**Resultados:**

| Escenario | Aprobación final | Default esperado | EL / monto | Margen / monto | Resultado / monto | Capital / EAD |
|---|---|---|---|---|---|---|
| Base | 64.7% | 10.7% | **2.99%** (verde) | 9.98% | 6.99% | 9.5% |
| Adverse | 50.0% | 12.5% | **3.91%** (rojo) | 10.45% | 6.54% | 10.2% |
| Severe | 36.5% | 14.6% | **5.28%** (rojo) | 10.98% | 5.70% | 11.5% |

## 6. El estabilizador automático

| Escenario | EL / monto con la política aplicada | EL / monto si la cartera se congelara | Absorbido por la política |
|---|---|---|---|
| Base | 2.99% | 2.99% | — |
| Adverse | 3.91% | 4.53% | **0.61 pp** |
| Severe | 5.28% | 6.80% | **1.52 pp** |

Este es el argumento técnico más importante de la sección: **como el corte está expresado en PD calibrada y no en puntaje fijo, un deterioro del entorno reduce sola la originación**. La aprobación cae de 64.7% a 50.0% y a 36.5%, y con ella la pérdida. El stress se paga en **volumen**, no en pérdida: el resultado sigue positivo en los tres escenarios (7.0%, 6.5% y 5.7%), pero el negocio se achica casi a la mitad en Severe.

El corolario operativo: si alguna vez se decide expresar el corte en puntaje fijo por simplicidad, **hay que reponer ese estabilizador con una regla de recalibración automática**, o la próxima caída del ciclo entra completa a la cartera.

## 7. Capital de riesgo

Aproximado con la fórmula IRB de Basilea para *other retail* (correlación entre 3% y 16% según PD, confianza 99.9%). No es el capital regulatorio del producto: es una vara común para comparar escenarios en unidades de capital y no solo de pérdida esperada.

| Escenario | Capital / EAD | Capital | RWA estimado | (EL + capital) / monto colocado |
|---|---|---|---|---|
| Base | 9.5% | S/ 243,030 | S/ 3.04 M | 6.9% |
| Adverse | 10.2% | S/ 226,417 | S/ 2.83 M | 8.5% |
| Severe | 11.5% | S/ 203,850 | S/ 2.55 M | 10.9% |

El capital **en soles baja** entre escenarios porque la cartera se achica más rápido de lo que sube el requerimiento unitario. La cartera no queda descapitalizada en ningún escenario, pero el Comité debe saber que un escenario Severe exige 2 puntos más de capital por cada sol prestado.

## 8. Recomendación ejecutiva

**Capacidad de crecimiento.** Con la política de 6.9 y el nivel de riesgo actual, la Caja puede colocar la cosecha completa con 2.99% de pérdida esperada, dentro del apetito restateado, y 7.0% de resultado sobre monto. El espacio para crecer **no está en subir el corte** —cada punto de aprobación cuesta pérdida esperada, cuantificado en 6.9— sino en tres palancas operativas: verificar más rápido el ingreso (convierte revisiones en aprobaciones), re-consultar el buró de las solicitudes sin score, y crecer en los segmentos de abajo.

**Segmentos a priorizar.** La **capacidad de pago** es la dimensión que más separa rentabilidad: con DTI post-crédito hasta 30% el resultado es 9.4% con 2.7% de pérdida esperada, contra 5.0% en el tramo 45-60% y 2.8% por encima de 60%. En score, la banda sobre 640 rinde 8.3% con 1.3% de pérdida. El crecimiento sano está en clientes con **holgura de cuota**, no en tickets grandes.

**Lo que el tablero desmiente.** El tamaño del crédito no separa rentabilidad (todos los tramos rinden entre 6.8% y 7.4%) y el territorio tampoco: las cinco regiones quedan entre 6.7% y 7.5%, con diferencias de ruido. No hay región que priorizar ni que castigar, lo que es coherente con el análisis de fairness de 6.8.

**Segmentos a vigilar o restringir.** La banda de score 580-600 concentra **35% de la pérdida esperada con 23% del monto** y rinde 5.4%: es donde un deterioro pega primero y lo primero que se recorta si el semáforo se pone en rojo. El DTI post-crédito sobre 60% rinde 2.8% y solo debe entrar vía contraoferta. El ticket sobre S/ 20,000 rinde bien (7.4%), así que no se restringe por rentabilidad: se mantiene en revisión obligatoria por su comportamiento errático y su peso en la exposición (6.4).

**Qué mirar para actuar.** Si la pérdida esperada de la cosecha supera 3.34%, primero se revisa la **calibración de la PD**, no el corte: la evidencia de 6.4 y 6.7 dice que el problema suele ser de nivel y no de ordenamiento. Si supera 3.89%, corresponde bajar el umbral de aprobación automática y escalar al Comité con la curva de trade-off de 6.9 como insumo.

## 9. Limitaciones

1. **La LGD y el factor de exposición son constantes**, porque 6.10 y 6.11 mostraron que ningún modelo les gana al baseline. Si en el futuro aparece señal, la capa de EL no cambia: solo cambian dos parámetros.
2. **El escenario aplica el shock a toda la cartera por igual.** No hay modelo macro ni sensibilidad por segmento: es un stress de nivel, no un modelo estructural, y así está declarado.
3. **La aprobación final asume que el analista aprueba el 60% de las revisiones**, igual que en 6.9. La sensibilidad a ese supuesto se documenta allí.
4. **El capital IRB es una aproximación comparativa**, no el requerimiento regulatorio peruano del producto.
5. **La LGD económica descuenta al mes final de recuperación**, porque el archivo no trae el calendario de cobros (6.11).

## 10. Trazabilidad del requisito 6.12

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Integrar PD, EAD y LGD a nivel cliente y cartera | §3 · `portfolio.expected_loss_frame` |
| Dashboard reproducible con exposición, PD, EAD, LGD, EL, aprobación, default y concentración | §4 · `reports/dashboard_cartera.html` · `el_tablero_segmentos.csv` |
| Tres escenarios (Base, Adverse, Severe) con shocks definidos y justificados | §5 · `el_escenarios.csv` · `fig33` |
| Cuantificar impacto en EL, aprobación, rentabilidad y capital de riesgo | §5, §6 y §7 · `el_estabilizador.csv`, `el_capital.csv` |
| Recomendación ejecutiva sobre crecimiento y segmentos | §8 |
