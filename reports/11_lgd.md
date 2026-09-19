# 6.11 · Modelo / estimación de LGD

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/08_ead_lgd.ipynb`; código en `src/severity.py`; tablas `lgd_*.csv`; figura `fig30`; artefacto `models/ead_lgd_v1.json`.

---

## 1. Resumen

- Variable respuesta: **LGD observada**, acotada en [0, 1], sobre los 671 créditos en default con información de recuperación (351 DEV, 161 VAL, 159 OOT). La identidad `(EAD − recuperaciones + costos) / EAD` se verifica con error máximo de 6 × 10⁻⁵.
- **Ningún modelo le gana al baseline fuera de muestra.** La logística fraccional mejora el MAE de VAL en 0.002 con R² negativo; el boosting sobreajusta (R² 0.27 en DEV, −0.14 en VAL).
- **Estimación adoptada: LGD contable global de 0.616** (promedio de los defaults de DEV), con MAE de 0.125 en VAL.
- **Aporte metodológico: la LGD del archivo no descuenta.** Con un workout medio de 12 meses, descontar al 10% anual la lleva de 0.623 a 0.660, y a la tasa media del contrato (31.9%), a 0.719: la pérdida esperada calculada con la LGD contable **subestima entre 6% y 15%**.
- **La severidad casi no cicla:** la peor cosecha de DEV y VAL da 0.626 contra 0.619 de promedio, un recargo de downturn de apenas 0.7 puntos. Confirma el hallazgo 13 de 6.4: la pérdida creció por frecuencia, no por severidad.

## 2. Descomposición de la pérdida

| Componente | Media | Percentil 5 | Mediana | Percentil 95 |
|---|---|---|---|---|
| Recuperación / EAD | 42.1% | 18.2% | 42.2% | 65.8% |
| Costo de recuperación / EAD | 4.4% | 1.3% | 4.5% | 7.6% |
| **LGD contable** | **62.3%** | 39.0% | 62.1% | 86.2% |
| Meses de workout | 12.0 | 3 | 11 | 25 |

Estabilidad entre cosechas: LGD de 0.615 a 0.634, recuperación de 0.411 a 0.429, costos de 0.041 a 0.046 y workout de 11.4 a 12.6 meses. Ninguna tendencia.

**Tratamiento de extremos.** No hay casos en 0 ni en 1: la distribución es unimodal entre 0.13 y 0.98, con 13 casos por encima de 0.95 y 3 por debajo de 0.20. Es una diferencia con la realidad —la LGD de carteras reales suele ser bimodal, con masa en recuperación total y en pérdida total— y es una característica del generador sintético que conviene declarar. Como no hay masa en los bordes, no hace falta un modelo de dos etapas (probabilidad de recuperación total + severidad condicional): basta un modelo para variable acotada.

## 3. Baseline segmentado vs. modelos

| Enfoque | MAE DEV | MAE VAL | Sesgo VAL | R² VAL |
|---|---|---|---|---|
| **Baseline global (adoptado)** | 0.110 | 0.125 | −0.010 | −0.004 |
| Baseline por plazo | 0.111 | 0.125 | −0.008 | −0.016 |
| Baseline por banda de buró | 0.110 | 0.125 | −0.014 | −0.012 |
| Baseline plazo × monto | 0.110 | 0.126 | −0.008 | +0.002 |
| Logística fraccional (8 variables de T0) | 0.108 | **0.124** | −0.015 | −0.003 |
| Boosting acotado | 0.094 | 0.133 | −0.016 | −0.136 |

**No hay señal en T0.** Los coeficientes estandarizados más grandes de la logística fraccional son los del ahorro sobre monto (−0.08) y el buró (−0.07); en DEV, las correlaciones más altas son buró (ρ = −0.095, p = 0.08) y tasa ofrecida (ρ = 0.10, p = 0.06), ninguna significativa. La mejora de 0.002 en el MAE de VAL no compensa sumar ocho variables, perder interpretabilidad y quedar con R² negativo.

**Se adopta el baseline global** por tres razones: empata en error, es el más estable de estimar con 351 casos y es el que un validador puede reproducir en una hoja de cálculo.

## 4. Precisión, sesgo y estabilidad por segmentos

Error del baseline en VAL, por banda de buró:

| Banda de buró | Casos | LGD observada | Estimada | Sesgo | MAE |
|---|---|---|---|---|---|
| ≤ 600 | 46 | 65.0% | 61.6% | −3.3 pp | 0.117 |
| 600-660 | 55 | 65.3% | 61.6% | −3.7 pp | 0.137 |
| 660-700 | 29 | 57.6% | 61.6% | +4.1 pp | 0.129 |
| > 700 | 28 | 59.8% | 61.6% | +1.9 pp | 0.102 |
| Sin score | 3 | 51.7% | 61.6% | +10.0 pp | 0.224 |

El sesgo cambia de signo entre bandas y el orden sugiere que los créditos de peor buró pierden algo más, lo mismo que insinuaba la correlación de −0.095. Con 29 a 55 casos por banda, **no alcanza para segmentar**: un baseline por banda de buró empeora el R² de VAL. Se deja documentado como hipótesis a reevaluar cuando haya más cosechas.

- **Sesgo global en VAL:** −0.010 (estima 0.616 contra 0.626 observado). Es chico, pero va en la dirección peligrosa (subestimar la pérdida), así que la LGD entra al monitoreo con revisión anual.
- **Confirmación en OOT:** 0.634 observado contra 0.616 estimado (+1.8 pp), dentro de la variación entre cosechas.

## 5. LGD económica: el número que sí cambia decisiones

La LGD del archivo **suma soles de momentos distintos**: recupera en promedio a los 12 meses y no descuenta. Basilea e IFRS 9 piden LGD económica, descontada a la tasa efectiva del contrato.

| Tasa de descuento | LGD económica | Diferencia vs. contable | Pérdida esperada relativa |
|---|---|---|---|
| 0% (contable, la del archivo) | 0.623 | — | 1.00 |
| 10% | 0.660 | +3.7 pp | 1.06 |
| 20% | 0.690 | +6.7 pp | 1.11 |
| 30% | 0.715 | +9.2 pp | 1.15 |
| 31.9% (tasa media del contrato) | 0.719 | +9.6 pp | 1.15 |

**Recomendación:** adoptar la LGD económica para provisiones y Expected Loss. Con una advertencia que importa: si se cambia la base de la métrica, hay que **restatear en la misma base el umbral de pérdida esperada del apetito** (6.1 lo fijó en 3% sobre la pérdida realizada sin descontar). Cambiar la métrica sin cambiar el umbral rompería el semáforo por definición, no por riesgo. Esa decisión conjunta —base y umbral— corresponde a 6.12, donde se integra la pérdida esperada de la cartera.

## 6. LGD de downturn

| Parámetro | Valor |
|---|---|
| Promedio de largo plazo (DEV + VAL) | 0.619 |
| Peor cosecha (2024) | 0.626 |
| **Recargo de downturn** | **+0.7 pp** |
| Confirmación OOT 2025 | 0.634 |

La severidad **casi no cicla**: entre la mejor y la peor cosecha hay 1.9 puntos, contra los 5.4 puntos que se movió la tasa de default en el mismo periodo. El escenario de stress de 6.12 debe cargar sobre la **PD**, que es la palanca real, y usar un recargo chico en LGD.

## 7. Limitaciones

1. **La LGD es unimodal y sin masa en los bordes**, a diferencia de una cartera real. Cualquier lectura sobre la forma de la distribución es del dato sintético, no del negocio.
2. **No hay información de workout más allá del total**: no se conocen pagos parciales ni su calendario, así que el descuento usa el mes final de recuperación como si todo se cobrara ahí. Es conservador respecto de recuperar antes y optimista respecto de recuperar después.
3. **Los campos de recuperación son posteriores al default** y, por definición, no pueden usarse como predictores: el modelo de LGD para Expected Loss en la originación solo puede usar variables de T0, que es lo que se hizo.
4. **351 defaults en DEV** limitan cualquier segmentación: la diferencia por banda de buró que insinúan los datos no es estimable con esta muestra.
5. Se asume que la LGD estimada sobre defaults observados aplica a los créditos que la nueva política aprobaría; si la mezcla cambia mucho, habrá que revalidar.

## 8. Trazabilidad del requisito 6.11

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Trabajar sobre cuentas en default con información de recuperación | §1 y §2 · `severity.build_severity_frame` |
| Baseline segmentado + modelo estadístico o de ML apropiado para variable acotada | §3 · logística fraccional y boosting acotado · `lgd_comparacion_modelos.csv` |
| Discutir recuperaciones, costos, tiempo de workout y tratamiento de extremos | §2 y §5 · `fig30` · `lgd_economica.csv` |
| Evaluar precisión, sesgo y estabilidad, incluyendo revisión por segmentos | §4 · `lgd_error_por_segmento.csv` · confirmación OOT |
