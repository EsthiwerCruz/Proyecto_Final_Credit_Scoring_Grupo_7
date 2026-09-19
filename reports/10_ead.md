# 6.10 · Modelo / estimación de EAD

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/08_ead_lgd.ipynb`; código en `src/severity.py`; tablas `ead_*.csv`; figuras `fig28` y `fig29`; artefacto `models/ead_lgd_v1.json`.

---

## 1. Resumen

- El producto es un **microcrédito amortizable sin garantía**: no hay línea, saldo utilizado ni monto no utilizado, y `ccf_observed` está vacío en el 100% de los casos. **No se fuerza un CCF revolvente**, tal como advierte la nota del caso.
- Variable respuesta: **factor de exposición** `ead_ratio = ead_at_default / requested_amount`, acotada en [0, 1]. Población: los 671 créditos en default (351 DEV, 161 VAL, 159 OOT).
- **Hallazgo de coherencia:** la mitad de los defaults tiene una exposición que exigiría más de 12 cuotas pagadas, imposible con un default definido dentro de los 12 meses. Por eso **no se estima la EAD como saldo teórico del calendario** y se declara la limitación.
- **Ningún modelo le gana al baseline fuera de muestra.** La logística fraccional pasa de R² 0.028 (DEV) a −0.046 (VAL); el boosting, de 0.286 a −0.133. Segmentar por plazo o por banda de buró tampoco aporta.
- **Estimación adoptada: factor global de 0.415**, el promedio de los defaults de DEV. Error absoluto medio en VAL de 0.159 y sesgo de +0.5 pp.

## 2. Variable respuesta y población

| Decisión | Definición | Por qué |
|---|---|---|
| Respuesta | `ead_at_default / requested_amount` | El producto es amortizable: la exposición se expresa como fracción del monto desembolsado, no como CCF sobre una línea que no existe |
| Población | Créditos con `default_12m_flag = 1` y exposición informada (671) | Son las únicas cuentas con EAD observada; el enunciado lo pide así |
| Muestras | DEV 351 · VAL 161 · OOT 159 | Mismo esquema temporal que PD: se ajusta en DEV, se compara en VAL y el OOT se mira una sola vez |
| Supuesto | Monto desembolsado = monto solicitado | El archivo no trae el desembolsado; queda declarado como supuesto |

`ead_at_default` coincide exactamente con `balance_at_default`: son la misma cifra con dos nombres, así que no aportan información distinta.

Distribución: media 0.418, mediana 0.412, desviación 0.187, rango de 0.04 a 0.94. Estable entre muestras (DEV 0.415, VAL 0.410, OOT 0.430) y entre cosechas (0.396 a 0.430).

## 3. Coherencia con el calendario de amortización

Antes de modelar hay que preguntarse si la exposición observada es **compatible con el producto**. Para un crédito francés de *n* cuotas y tasa mensual *r*, el saldo tras *k* pagos es conocido; despejando *k* se obtiene cuántas cuotas tendría que haber pagado el cliente para llegar a esa exposición.

| Estadístico | Cuotas implícitas (tasa del contrato) | Cuotas implícitas (TEA de referencia) |
|---|---|---|
| Mediana | 11.6 | 11.6 |
| Percentil 75 | 28.0 | 27.7 |
| Percentil 95 | 45.7 | 45.5 |
| % por encima de 12 cuotas | **49.3%** | **49.3%** |
| % por encima del plazo contratado | 0% | 0% |

**La mitad de los defaults tiene una exposición que no es alcanzable dentro de la ventana de 12 meses.** La lectura benigna es que hubo prepagos parciales; la lectura de calidad de datos es que la exposición del archivo se generó con independencia del calendario de amortización. El resultado no cambia con la tasa que se use para reconstruir el saldo, así que no es un artefacto del supuesto de tasa.

**Consecuencia metodológica:** queda descartado el enfoque natural para un amortizable —estimar el saldo teórico en el mes del default— porque además el archivo no trae fecha de default. Se modela el factor de exposición directamente. En una cartera real, este chequeo sería un hallazgo para el dueño del dato **antes** de calcular provisiones.

## 4. Baseline segmentado vs. modelos

Todos se ajustan con los defaults de DEV y se comparan en VAL. La logística fraccional (Papke-Wooldridge) es el modelo estadístico correcto para una respuesta acotada: predice siempre dentro de [0, 1], a diferencia de una regresión lineal.

| Enfoque | MAE DEV | MAE VAL | Sesgo VAL | R² VAL |
|---|---|---|---|---|
| **Baseline global (adoptado)** | 0.151 | **0.159** | +0.005 | 0.000 |
| Baseline por plazo | 0.151 | 0.159 | +0.006 | +0.004 |
| Baseline por banda de buró | 0.150 | 0.161 | +0.009 | −0.018 |
| Baseline plazo × monto | 0.148 | 0.157 | +0.013 | −0.009 |
| Logística fraccional (8 variables de T0) | 0.149 | 0.163 | +0.003 | −0.046 |
| Boosting acotado | 0.129 | 0.170 | +0.010 | −0.133 |

Tres lecturas:

1. **Ninguna variable de T0 explica la exposición.** En DEV, la correlación más alta es la de la edad (ρ = 0.11, p = 0.03), que no sobrevive a corregir por las nueve pruebas hechas; buró, plazo, monto, ingreso y capacidad quedan todos con p > 0.09.
2. **El boosting es el caso de manual de sobreajuste:** R² 0.286 en 351 casos de ajuste y −0.133 fuera de muestra. Memoriza.
3. **Segmentar no ayuda.** El factor es plano entre tramos de plazo (0.409 a 0.423), que es justo la variable que en teoría debería moverlo. Es coherente con el hallazgo de §3: si la exposición no sigue el calendario, el plazo no puede explicarla.

## 5. Error, sesgo y estabilidad por segmentos

- **Sesgo global en VAL:** +0.005 sobre una media de 0.410 (el baseline de DEV es 0.415). Es un sesgo conservador y pequeño.
- **Por tramo de plazo en VAL:** el sesgo se mueve entre −0.02 y +0.03 y cambia de signo, es decir, ruido y no heterogeneidad sistemática.
- **Entre cosechas:** de 0.396 (2021) a 0.430 (2025), sin tendencia.
- **Confirmación en OOT:** 0.430 observado contra 0.415 estimado (+1.5 pp). Va en la dirección conservadora que hay que vigilar, está dentro de la variación entre cosechas y **no justifica cambiar el parámetro**.

El MAE de 0.159 sobre una media de 0.41 es alto en términos relativos, pero es **irreducible con esta información**: la desviación estándar del propio dato es 0.187, así que el baseline ya captura casi toda la varianza explicable.

## 6. Limitaciones

1. **La exposición del archivo no es coherente con el calendario de amortización** (§3). Es la limitación principal y condiciona todo el enfoque.
2. **No hay fecha de default**, así que no se puede construir la EAD como saldo en el mes del incumplimiento ni analizar cómo evoluciona la exposición con la antigüedad.
3. **Se asume monto desembolsado = monto solicitado**, porque el archivo no distingue ambos.
4. **351 defaults en DEV** es poco para cualquier modelo con varias variables; el resultado de esta sección es en parte una consecuencia del tamaño de muestra, no solo de la ausencia de señal.
5. El factor se aplica sobre el monto **recomendado** en el motor de decisión, no sobre el solicitado, cuando hay contraoferta: es coherente con la definición, pero supone que la relación exposición/monto no cambia al reducir el monto.

## 7. Trazabilidad del requisito 6.10

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Definir claramente la variable respuesta y la población | §2 · `severity.build_severity_frame` |
| Producto amortizable: estimar EAD con metodología defendible y contrastarla con un baseline segmentado | §4 · `ead_comparacion_modelos.csv` · `fig29` |
| No forzar un CCF revolvente si no corresponde | §1 y §2 · `ccf_observed` vacío y producto sin línea |
| Evaluar error, sesgo y estabilidad por segmentos | §5 · `ead_error_por_segmento.csv` |
| Documentar limitaciones | §3 y §6 · `fig28` |
