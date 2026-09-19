# 6.4 · EDA orientado a riesgo

**Caso 15 · Caja Rural 360 — Microcrédito rural para independientes**

> **Evidencia:** `notebooks/02_eda_riesgo.ipynb`; tablas en `reports/tables/` (prefijo `eda_`) y figuras `fig11` a `fig18`.

---

## 1. Resumen

- **La señal de riesgo está concentrada.** De 22 candidatas, solo 5 tienen asociación con el default en DEV después de corregir por comparaciones múltiples: el score de buró, la carga de deuda (`dti`, `dti_post`), la mora previa y la cuota de deudas vigentes. Todo lo demás es ruido en esta cartera.
- **El deterioro 2021-2024 es de nivel, no de capacidad de ordenar.** A igual score, VAL tiene 0.42 log-odds más de default (odds 1.52 veces mayores), pero la pendiente no cambia. Y no fue un salto en 2023: es una tendencia de odds ×1.20 por año.
- **La capacidad de pago tiene un umbral en 45% de DTI post-crédito**, y se suma al buró en lugar de interactuar con él: un scorecard aditivo captura bien la estructura.
- **Crecer fuera de agencias no deterioró la cartera en DEV** y ni el territorio, ni la distancia, ni el tamaño del hogar, ni la edad ordenan el riesgo. El ingreso en efectivo solo muestra algo más de riesgo en el quintil más alto y de forma inestable. Es la respuesta directa al desafío del caso: **no hay evidencia para excluir por falta de trazabilidad bancaria**.
- **La pérdida creció por frecuencia, no por severidad** (LGD estable en 61.5%-62.6%), y se concentra en los dos quintiles más bajos del buró: 39% de los créditos explican el 65% de la pérdida. Ahí es donde el punto de corte de 6.9 tiene que trabajar.

## 2. Reglas de uso de las muestras

Coherentes con 6.2 y 6.3, para que ningún hallazgo contamine la evaluación final:

| Muestra | Uso en 6.4 |
|---|---|
| DEV 2021-2023 (3,443 créditos, 351 defaults) | Todas las relaciones variable-riesgo que informan decisiones |
| VAL 2024 (1,151 créditos, 161 defaults) | Comprobar si el hallazgo se sostiene fuera de DEV; **no decide** |
| OOT 2025 | **No se abre variable por variable.** Solo entran sus agregados de cartera ya publicados en 6.1-6.2 y métricas sin target (PSI) |

Todas las tasas llevan intervalo de Wilson, el tamizaje corrige por comparaciones múltiples (Benjamini-Hochberg) y cada afirmación de segmento indica su p-valor: con 22 variables y varios segmentos, algo "significativo" aparece por azar si no se controla.

**Limitación declarada.** El archivo trae el flag de default a 12 meses, pero no la fecha del default ni la mora mes a mes. No se pueden construir curvas de vintage por meses en libros; se analizan **cohortes de originación con su tasa a 12 meses** (trimestrales).

## 3. Hallazgos accionables

### 3.1 Qué variables tienen señal

**Hallazgo 1 · La señal está concentrada.** Solo `bureau_score`, `dti`, `dti_post`, `prior_delinquencies_24m` y `monthly_debt_payment` tienen q < 0.05 en DEV; `ahorro_sobre_monto` queda al borde (q = 0.06). Ninguna categórica (región, canal, tipo de empleo) pasa el filtro.
*Impacto:* scorecard **parsimonioso**; agregar variables sin señal suma ruido y sobreajuste (6.5 lo confirma con la mora previa).

**Hallazgo 2 · El buró es el eje del riesgo y ordena igual en el tiempo y en todos los canales.** En DEV el default cae de 26.6% en el decil más bajo a 2.4% en el más alto; el AUC por año se mueve entre 0.67 y 0.71 sin tendencia y por canal entre 0.66 y 0.71.
*Impacto:* característica principal del scorecard, con tramos monótonos. Como ordena igual en los cuatro canales, **no hace falta un scorecard por canal**.

### 3.2 El deterioro del riesgo en el tiempo

**Hallazgo 3 · Es un desplazamiento de nivel, no una pérdida de capacidad de ordenar.** A igual score, VAL tiene +0.42 log-odds (OR 1.52, p < 0.001) y la pendiente del buró no cambia (p = 0.49).
*Impacto:* un scorecard ajustado en DEV ordena bien en 2024 pero **subestima la PD**; hay que separar el score (orden) de la tabla score → PD (nivel), que es la que se recalibra en 6.7.

**Hallazgo 4 · No fue un salto en 2023: es una tendencia gradual.** Las cohortes trimestrales 2021-2024 muestran odds de default creciendo 20% por año (p < 0.001); un escalón en 2023 no agrega nada sobre la tendencia (p = 0.38). El default trimestral pasa de 9.5% (2021T1) a 17.1% (2024T4).
*Impacto:* el nivel de PD envejece rápido. Se necesita calibrar con la ventana más reciente, un disparador de recalibración por brecha entre PD predicha y default observado, y un escenario Adverse que prolongue la tendencia. El monitoreo compara cohortes trimestrales, no solo años.

### 3.3 Capacidad de pago

**Hallazgo 5 · La capacidad de pago tiene un umbral.** Con DTI post-crédito de hasta 45% el default es plano (8.6% y 8.0% en DEV); entre 45% y 60% sube a 11.2% y entre 60% y 80% a 15.5%. VAL repite el quiebre en 45%.
*Impacto:* un término lineal subestimaría el quiebre; el tramo "≤ 45% sin penalidad" refleja el dato y sustenta la regla de capacidad de 6.1 (automático hasta 45%, tope duro en 60%).

**Hallazgo 6 · Buró y capacidad se suman, no interactúan.** En DEV el default va de 3.1% (buró alto, capacidad holgada) a 24.3% (buró bajo, capacidad ajustada) y los términos de interacción no aportan (p = 0.90).
*Impacto:* un scorecard aditivo captura la estructura; no hay que esperar que un modelo de ML gane por interacciones entre estas dos variables. La política se puede expresar como matriz de banda de score × capacidad.

**Hallazgo 7 · La mora previa ordena en DEV, pero no se sostiene en VAL.** DEV: 8.8% (sin moras), 11.7% (una) y 12.8% (dos o más), en cada uno de los tres años. VAL: 14.7%, 11.9% y 17.0%.
*Impacto:* candidata por DEV, pero debe probar que no se invierte antes de entrar al scorecard (criterio S6 de 6.5, que finalmente la deja fuera).

### 3.4 Crecimiento, canales y fairness

**Hallazgo 8 · Crecer por canales digitales no aumentó el riesgo en DEV, pero la web se aparta en 2024.** En DEV el default por canal va de 8.9% (alianza) a 11.6% (agencia), sin diferencia (p = 0.46), con 69% de la cartera originada por app y web. En VAL la web sube a 17.8% frente a 10.9%-12.3% del resto (p = 0.04). Es una señal de un año entre varias pruebas de segmento: es alerta, no conclusión.
*Impacto:* el canal no entra al modelo y la evidencia de DEV respalda crecer fuera de agencias. Se agrega un **KRI de default por canal** y conviene revisar los controles de identidad del flujo web.

**Hallazgo 9 · La brecha de los clientes nuevos crece cada año.** −0.5 pp (2021), +0.6 pp (2022), +3.4 pp (2023) y +4.7 pp (2024, p = 0.03). En DEV agregado no es significativa (p = 0.26), así que un scorecard ajustado en DEV no la captura.
*Impacto:* riesgo de **subestimar a los clientes nuevos en producción**. Monitoreo por cohorte, límite de concentración del apetito, monto acotado del primer crédito y reevaluación en la próxima recalibración.

**Hallazgo 10 · El ingreso en efectivo solo muestra algo más de riesgo en el quintil más alto, y no de forma estable.** DEV: 11.8% frente a 9.4%-10.4% del resto (p = 0.14). VAL: 18.7% frente a 10.4%-15.0% (p = 0.03).
*Impacto:* no hay necesidad de negocio para usar la informalidad en el modelo, y usarla contradice el objetivo del caso. Se aplica **verificación del ingreso** en tickets altos (6.1 §8), se monitorea el segmento y se mantiene el AIR por efectivo en el apetito.

**Hallazgo 11 · Territorio, distancia, dependientes y edad no cambian el riesgo.** Región sin diferencias en DEV (p = 0.13) ni en VAL (p = 0.41), y la región de menor default cambia de muestra (Sur en DEV, Oriente en VAL). La distancia es plana hasta 50 km; dependientes y edad no muestran patrón.
*Impacto:* se **excluyen del scorecard por diseño** y 6.5 verifica que excluirlas no cuesta poder predictivo (ninguna supera el IV mínimo). Se conservan para medir fairness en 6.8.

### 3.5 Exposición y pérdida

**Hallazgo 12 · Monto y plazo no ordenan la PD, pero el ticket grande es inestable y concentra exposición.** AUC de 0.50 en ambas. Los créditos sobre S/ 20,000 son ~4% de las operaciones y ~14% del monto, y su riesgo se invirtió: 2.8% de default en DEV (4 de 143, p = 0.001) y 26.2% en VAL (11 de 42, p = 0.04), con el 22.6% de la pérdida de 2024.
*Impacto:* el monto no entra al modelo como PD. El ticket grande se gestiona con **límites de concentración, revisión obligatoria y monto máximo por capacidad de pago**; en Expected Loss y stress (6.12) se mira en monto, no en número de créditos.

**Hallazgo 13 · La pérdida creció por frecuencia, no por severidad.** Entre 2021 y 2024 el default pasó de 8.6% a 14.0% y la pérdida sobre monto de 1.9% a 4.0%, mientras la LGD se mantuvo entre 61.5% y 62.6% (p = 0.83) y la EAD entre 40% y 43% del monto.
*Impacto:* la PD es la palanca de la Expected Loss. Para LGD basta un baseline segmentado contra el cual comparar el modelo de 6.11, y el shock principal del stress va a la PD.

**Hallazgo 14 · La pérdida se concentra en los dos quintiles más bajos del buró.** En DEV, el quintil más bajo tiene 20% de los créditos, 42% de los defaults y 40% de la pérdida; los dos quintiles bajos suman 65% de la pérdida con 39% de los créditos. VAL, con los mismos cortes, repite el patrón (59%).
*Impacto:* base cuantitativa del punto de corte (6.9): la zona de rechazo y revisión se define en los tramos bajos del score, donde cada punto de aprobación resignado ahorra más pérdida.

## 4. Composición de la cartera (DEV)

| Segmento | % de créditos | % del monto | Default | Pérdida / monto |
|---|---|---|---|---|
| Canal digital (app + web) | 68.5% | 68.7% | 9.9% | 2.3% |
| Agencia y alianza | 31.5% | 31.3% | 10.8% | 2.7% |
| Lima | 41.2% | 41.1% | 11.4% | 2.5% |
| Clientes nuevos | 45.0% | 45.4% | 10.8% | 2.5% |
| Efectivo > 80% del ingreso | 17.8% | 17.2% | 11.3% | 3.0% |
| Sin score de buró | 3.7% | 3.4% | 4.8% | 1.0% |
| DTI post-crédito > 45% | 41.3% | 45.1% | 13.0% | 2.8% |
| Monto > S/ 20,000 | 4.2% | 14.3% | 2.8% | 0.5% |

La lectura importa para el apetito: el segmento que más pesa en riesgo no es un canal ni una región, sino la **capacidad de pago ajustada** (41% de los créditos y 45% del monto, con 13.0% de default).

## 5. Consecuencias para el modelo y la política

| Decisión | Hallazgo que la sustenta |
|---|---|
| Scorecard parsimonioso, aditivo, con tramos monótonos | H1, H2, H6 |
| Separar score (orden) de la tabla score → PD (nivel) y recalibrar | H3, H4 |
| Regla de capacidad 45% / 60% sobre `dti_post` | H5 |
| Exigir que una variable no se invierta en VAL antes de entrar al scorecard | H7 |
| Canal, región, distancia, dependientes, edad y efectivo fuera del modelo | H8, H10, H11 |
| Verificación de ingreso en efectivo alto y ticket alto, sin penalizar | H10, H12 |
| Límites de concentración y revisión obligatoria en tickets grandes | H12 |
| Punto de corte y zona de revisión en los tramos bajos del score | H14 |
| Monitoreo: default por canal, brecha de clientes nuevos, cohortes trimestrales | H4, H8, H9 |
| Stress con shock sobre PD; LGD con baseline segmentado | H13 |

## 6. Trazabilidad del requisito 6.4

| Requisito del enunciado | Dónde se cumple |
|---|---|
| EDA que responde preguntas de riesgo y negocio | Secciones 1 a 10 del notebook, una pregunta por sección |
| Bad rate por segmentos y composición de cartera | §3.4, §4 · `eda_mapa_segmentos_dev.csv` · `fig15`, `fig16` |
| Cohortes / vintages | §3.2 · `eda_cohortes_trimestrales.csv` · `fig13` (limitación de MOB declarada en §2) |
| Tendencias temporales | H3, H4, H9, H13 · `fig13`, `fig17` |
| Relaciones no lineales | H5, H6 · `eda_capacidad_dti_post.csv` · `fig14` |
| 10+ hallazgos accionables con evidencia, interpretación e impacto | 14 hallazgos en §3 · `eda_hallazgos.csv` |
