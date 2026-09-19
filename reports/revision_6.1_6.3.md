# Registro de revisión · Secciones 6.1, 6.2 y 6.3

**Caso 15 · Caja Rural 360**

Revisión metodológica del avance de 6.1-6.3 antes de pasar a 6.4. Cada cambio tiene evidencia reproducible en el repositorio (código en `src/`, prueba en `tests/`, salida en los notebooks y tablas en `reports/tables/`).

**Criterios aplicados**

- Se modifica solo lo que la evidencia sostiene; lo que no la tiene se rotula como supuesto.
- Toda decisión sobre variables se toma **solo con DEV**. VAL se muestra como información y la cosecha OOT (2025) no se consulta para decidir, como fija 6.2.
- **No cambian:** la población PD, el target, el split DEV/VAL/OOT, la lista de variables prohibidas, la exclusión de la tasa ofrecida ni los umbrales del Risk Appetite.

---

## 1. Resumen

| # | Hallazgo | Evidencia | Decisión |
|---|---|---|---|
| 1 | Se afirmaba una estacionalidad del default (pico en octubre, campaña agrícola) que no existe | Chi² mes × default p = 0.89; el rango entre meses (4.2 pp) es menor que el típico bajo azar (4.7 pp); setiembre-diciembre 11.9% vs 11.5% (p = 0.66); en DEV la campaña tiene **menos** default | Se retira de 6.1 y 6.2 y se descarta `campana_siembra`. El split por años calendario se mantiene por comparabilidad, no por estacionalidad |
| 2 | La evaluación de variables usaba max(AUC, 1 − AUC), que pierde el signo y está sesgado hacia arriba | Una variable aleatoria marca 0.513 en DEV y 0.519 en VAL; `antiguedad_relativa` y `excedente_per_capita` cambian de signo en VAL sin que la tabla lo mostrara | Evaluación con AUC con dirección, p-valor (Mann-Whitney) y aporte incremental (test de razón de verosimilitud) |
| 3 | Se afirmaba que las derivadas aportaban señal, sin probar si agregaban algo a sus componentes | Protocolo R1-R5 en DEV (sección 3) | Se conservan 2 candidatas (`dti_post`, `ahorro_sobre_monto`) y se descartan 8 con motivo documentado |
| 4 | Se afirmaba que los faltantes eran informativos (thin-file, sin producto de ahorro) | Los tres son compatibles con MCAR; quien no tiene score tiene el mismo historial de buró; el archivo trae `dti` aun sin ingreso (145 créditos) | Imputación con mediana sin indicador dentro del modelo; `dti` se recalcula en el pipeline; indicadores solo para política y monitoreo |
| 5 | `dti_post_verificable` castigaba por construcción el ingreso en efectivo | No agrega sobre `dti_post` (p = 0.23); el efecto del efectivo es débil e inestable (DEV 11.3% vs 10.0%, p = 0.34; 2024 20.3% vs 12.6%) | Se descarta del modelo; la verificación de ingreso queda como disparador de revisión en la política, sin penalizar |
| 6 | El apetito no decía qué prevalece si la aprobación choca con los límites de riesgo | Factibilidad 2021-2024: con 70% de aprobación el default va de 5.8% a 10.2% y la EL de 1.4% a 2.9%; en 2024 la aprobación máxima con ambos límites es 72% (manda la EL) | Umbrales sin cambios; se agrega el tipo de cada métrica y una regla de precedencia |

---

## 2. Estacionalidad (cambio 1)

**Por qué importa.** La estacionalidad no es un análisis estándar del scoring de originación. El problema era que el avance la usaba como **evidencia** en tres lugares: la necesidad financiera de 6.1, un sesgo y una justificación del split en 6.2, y una variable en 6.3.

**Prueba** (`quality.seasonality_test`, notebook 00 §4, `tables/estacionalidad_mensual.csv`, `fig04`):

- Chi² de independencia mes × default: p = 0.889 (solo DEV: p = 0.709; el mes más riesgoso en DEV es abril).
- El rango observado entre meses (4.2 pp) se compara con 5,000 simulaciones de azar con los mismos tamaños mensuales: mediana 4.7 pp, p95 6.8 pp, p = 0.66.
- Setiembre-diciembre vs resto: 11.9% vs 11.5% (Fisher p = 0.66).

**Cambios:** 6.1 §2 (necesidad financiera), 6.2 §6 (sesgo "Calendario"), §7 (justificación y alternativas del split) y §8 (mes de originación); `config.py` (comentario del split); `features.py` (`campana_siembra` pasa al pool de descartadas).

---

## 3. Evaluación y pre-selección de variables derivadas (cambios 2 y 3)

**Protocolo** (`features.screen_derived_features`, `config.SCREEN_*`). Una derivada se conserva si cumple las cinco reglas:

| Regla | Criterio |
|---|---|
| R1 | Señal en DEV con el signo esperado (Mann-Whitney, p < 0.05) |
| R2 | Mantiene el signo esperado en 2021-2022 y en 2023 |
| R3 | Aporta sobre el núcleo (buró + dti) y sus propios componentes (p < 0.10) |
| R4 | Si usa una variable sensible, esta aporta sobre la versión sin ella (p < 0.05) |
| R5 | No es redundante (Spearman > 0.70) con otra derivada que pasa R1-R4 |

**Resultado** (`tables/features_evaluacion.csv`, `fig10`):

| Decisión | Variables |
|---|---|
| Conservadas | `dti_post`, `ahorro_sobre_monto` |
| Descartadas por R1-R2 (sin señal o signo inestable) | `campana_siembra`, `intensidad_busqueda`, `antiguedad_relativa`, `loan_to_income` |
| Descartada por R3 (no agrega sobre sus componentes) | `deuda_por_obligacion` |
| Descartadas por R3-R4 (y usan una variable sensible) | `dti_post_verificable`, `excedente_per_capita` |
| Descartada por R5 (redundante) | `colchon_ahorro_meses` (con `ahorro_sobre_monto`) |

**Sobre `dti_post`.** Es intercambiable con `dti` (Spearman 0.83). En un logit lineal `dti` aporta algo sobre `dti_post` (p = 0.02) y no al revés (p = 0.61), pero por tramos, que es como trabaja un scorecard, ninguna aporta sobre la otra (p = 0.22 y 0.21), y en VAL tampoco. Se prefiere `dti_post` por razones de negocio: la PD reacciona si se contraoferta monto o plazo, y coincide con la regla de capacidad de pago. El texto anterior ("aporta información que ninguna variable original tenía") se corrigió.

**Cambios:** `validation.py` (`auc_raw`, `auc_test`, `lr_test`, `lr_test_binned`; `univariate_auc` queda documentado como magnitud sin dirección), `features.py` (`build_candidate_pool`, `screen_derived_features`, `rules_doc`, `discarded_doc`), `pipeline.py` (la matriz pasa de 42 a 32 columnas), 6.3 §3 y notebook 01 §8.

---

## 4. Faltantes y `dti` sin ingreso (cambio 4)

**Pruebas** (`quality.missingness_report`, `quality.bureau_history_check`, notebook 01 §2):

| Prueba | `monthly_income` | `bureau_score` | `savings_balance` |
|---|---|---|---|
| Tasa por año (chi²) | p = 0.52 | p = 0.15 | p = 0.65 |
| Relación con la aprobación | p = 0.41 | p = 0.54 | p = 1.00 |
| Logit del faltante con 26 variables de T0 | p = 0.54 · AUC CV 0.50 | p = 0.38 · AUC CV 0.51 | p = 0.34 · AUC CV 0.51 |
| Default con faltante, controlado por el núcleo (DEV) | p = 0.70 | p = 0.02, solo por 2021-2022 | p = 0.31 |
| Default con / sin faltante en 2023 | 10.5% / 12.4% | 12.5% / 12.4% | 10.8% / 12.5% |

- **Sin score no es thin-file.** Tienen el mismo historial de buró que el resto: 88.6% con al menos una deuda activa, 43.2% con mora previa, mismas consultas (KS con p > 0.5).
- **Ahorro faltante no es "sin producto de ahorro".** Falta igual en clientes nuevos (7.9%) y antiguos (7.5%).
- **`dti` sin ingreso.** Las 145 filas sin ingreso traen `dti`, imposible si `dti` = cuota / ingreso. Usarlo sería entrenar con un dato que el servicio de scoring no tendrá.

**Decisiones:** `build_features` recalcula `dti` desde sus insumos (sin ingreso queda faltante); imputación con la mediana de DEV (para el score, riesgo neutral); `flag_sin_buro`, `flag_sin_ingreso` y `flag_sin_ahorro` salen de la matriz del modelo y quedan para política y monitoreo; nueva regla de consistencia "dti informado con ingreso faltante" (145 casos, severidad media). Para 6.5: bins de faltante con WOE neutral.

**Cambios:** `features.py`, `pipeline.py` (entrada de 19 columnas, sin `dti` ni fecha), `quality.py`, `data.py` y `data_dictionary.py` (racional e imputación), 6.1 §3 y §8, 6.2 §4, 6.3 §1, §2.1, §2.3 y §4.

---

## 5. Ingreso en efectivo (cambio 5)

| Muestra | Default con más de 80% en efectivo | Resto | p |
|---|---|---|---|
| DEV 2021-2023 | 11.3% (n = 613) | 10.0% | 0.34 |
| VAL 2024 (información) | 20.3% (n = 212) | 12.6% | 0.006 |

La asociación es positiva pero débil en DEV y se intensifica en 2024 (DEV + VAL, controlando por buró, `dti` y muestra: OR 1.36, p = 0.01; interacción con 2024 p = 0.05). No justifica una penalidad continua dentro del modelo, que además iría contra el objetivo del caso. Se mantiene el disparador de revisión "efectivo > 80% y monto > S/ 10,000", reencuadrado como **verificación del ingreso declarado**: si no se sustenta, se ajusta el monto en lugar de rechazar. `cash_income_share` sigue como candidata con revisión de fairness para 6.5 y 6.8.

**Cambios:** `features.py` (`dti_post_verificable` e `ingreso_verificable` salen del pipeline), `data.py` (racional), 6.1 §8 y 6.3 §3.

---

## 6. Risk Appetite (cambio 6)

**Factibilidad** (`risk_appetite.appetite_feasibility`, `tables/risk_appetite_factibilidad.csv`). Se ordena toda la población de cada año solo por buró y se simula aprobar el mejor X%. A los rechazados que entran se les imputa el default y la pérdida de los aprobados de su decil de score (*parceling*). Solo años de DEV y VAL.

| Año | Default con 70% | EL con 70% | Aprobación máxima con default ≤ 11% y EL ≤ 3% |
|---|---|---|---|
| 2021 | 5.8% | 1.4% | 100% |
| 2022 | 7.2% | 1.8% | 100% |
| 2023 | 7.9% | 2.1% | 93.3% |
| 2024 | 10.2% | 2.9% | 72.0% |

Los umbrales son coherentes y no se cambian. Como en un año tipo 2024 el margen es de dos puntos, se agregan el **tipo de métrica** (`METRIC_TYPE`: la aprobación es objetivo de negocio; default, EL, LGD y capacidad son límites de riesgo) y la **regla de precedencia** (`PRECEDENCE_RULE`): si la aprobación choca con un límite de riesgo, prevalece el límite y no se relaja el punto de corte.

**Cambios:** `risk_appetite.py`, 6.1 §1, §5, §5.1 y S10, notebook 00 §6.

---

## 7. Correcciones menores

- **Región.** Oriente **y Sur** tienen la menor aprobación y el menor default (9.5% y 9.4%); las diferencias entre regiones tienen p ≈ 0.05, así que se presentan como indicio.
- **Distancia.** "Cuesta más atenderlos" pasa a ser un supuesto: el costo de recuperación sobre la EAD no crece con la distancia (Spearman 0.03, p = 0.48 en los defaults de 2021-2024; notebook 00 §6).
- **"Thin-file"** se reemplaza por "sin score de buró" en toda la documentación, incluido el límite por operación (el tope inicial se justifica porque el modelo no puede usar su variable principal).
- **Notebook 00.** Se agregó el encabezado de la sección 7 que citaba 6.2. Ambos notebooks se ejecutan de arriba abajo en una sola corrida (conteos 1..n).
- **Dependencias.** `scipy==1.15.3` declarado en `requirements.txt` (compatible con Python 3.10 y ya requerido por scikit-learn).

---

## 8. Pendientes para el equipo

- `reports/01_negocio_y_arquitectura_crediticia.md` cita `Ciclo_End_To_End.xlsx`, que no está en el repositorio: agregarlo (por ejemplo, en `docs/`) o quitar la referencia.
- En 6.5, elegir **una** entre `dti` y `dti_post`, y **una** entre `savings_balance` y `ahorro_sobre_monto`, y asignar WOE neutral a los bins de faltante.
- Recalcular la factibilidad del apetito con el modelo final (reemplazando el ordenamiento solo por buró).

---

## 9. Cómo verificar

```bash
pip install -r requirements.txt
python -m pytest tests          # 26 pruebas
jupyter nbconvert --to notebook --execute --inplace notebooks/00_negocio_y_poblacion.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/01_calidad_y_features.ipynb
```

Ambos notebooks regeneran `data/processed/`, `reports/tables/` y `reports/figures/` con semilla fija (`config.SEED = 42`).

---

# Anexo · Auditoría de 6.1 a 6.9 (antes de iniciar 6.10)

Revisión completa de lo construido hasta 6.9: contraste de cada cifra citada en los reportes contra las tablas generadas, revisión lógica de las reglas y búsqueda de contradicciones entre narrativa y código.

## Lo que estaba mal y se corrigió

| # | Hallazgo | Evidencia | Corrección |
|---|---|---|---|
| A1 | El motor rechazaba por PD **antes** de aplicar las reglas duras, así que rechazaba en automático solicitudes sin score de buró o sin ingreso, justo lo contrario de lo que dicen 6.1 y 6.8 | 2024: 8 de 45 sin score y 4 de 32 sin ingreso terminaban en REJECT; 2025: 7 y 2 | Las reglas por **falta de información** pasan antes del rechazo: sin score o sin ingreso van siempre a REVIEW, porque la PD se calculó con un insumo imputado. Las reglas de **verificación** (ticket alto, efectivo alto) siguen después del rechazo, para no gastar capacidad de análisis en casos con toda la información y PD fuera del apetito. Prueba `test_sin_informacion_nunca_se_rechaza_en_automatico` |
| A2 | `dti_hard_max` (el tope de 60% de 6.1) era un parámetro muerto: no se usaba en ninguna decisión | 1 sola aparición en el módulo | Ahora define el **monto que recibe el analista** cuando la capacidad no alcanza al 45%: 110 solicitudes de 2024 pasan de "sin monto viable" a una contraoferta concreta. Prueba `test_revision_por_capacidad_recibe_un_monto_viable_al_tope_duro` |
| A3 | El semáforo del apetito marcaba la revisión manual como cumplida usando una tolerancia de 3 puntos no declarada | 22.4% contra un límite de 20% aparecía en verde | El semáforo reporta el incumplimiento y cuantifica la cola (45 casos al año), con la regla de priorización por valor esperado |
| A4 | El disparador de revisión por distancia > 50 km de 6.1 §8 no estaba implementado y no se explicaba por qué | 21 solicitudes en 2024 | Se documenta la decisión en 6.9: 6.4 mostró que ese segmento no tiene peor default, peor LGD ni mayor costo de recuperación (Spearman 0.03, p = 0.48), así que mantenerlo gastaría capacidad y penalizaría a la población que el caso busca incluir |
| A5 | Cifras con redondeo inconsistente entre reportes (0.349 vs 0.348 de Gini; 23.3% vs 23.2% de revisión) | Contraste automático contra las tablas | Unificadas con el valor que imprimen los notebooks |
| A6 | En 6.8 la tabla de tres clientes mostraba la PD original y no la recalculada tras la contraoferta, y listaba una razón de más en el caso rechazado | `fairness_casos_explicados.csv` | Se usa la PD del motor y las razones que devuelve el modelo |

## Lo que se verificó y está correcto

- **Ninguna muestra se contamina.** Ningún notebook ajusta nada con OOT: binning, coeficientes y modelos se entrenan con DEV; el calibrador de Platt se ajusta con VAL; el OOT solo se evalúa en 6.7 y se confirma la política en 6.9.
- **Los umbrales de la política están en la escala de PD calibrada** y coinciden con los del artefacto `politica_decision_v1.json`.
- **Todas las cifras clave de los reportes 6.6 a 6.9 coinciden con las tablas generadas** (Gini, KS, O/E, AIR, swap, pricing y resultados de la política).
- **Todas las figuras citadas existen** y los reportes apuntan a tablas que se regeneran con los notebooks.
- **Reproducibilidad:** los ocho notebooks corren desde cero en copia limpia y regeneran tablas, datos procesados y artefactos idénticos, con la única excepción documentada de la columna de latencia (mide milisegundos y depende de la máquina).
- **62 pruebas automáticas**, incluidas las dos nuevas que fijan las correcciones A1 y A2.

## Efecto de las correcciones sobre los resultados

| Métrica (2024) | Antes | Después |
|---|---|---|
| Aprobación automática | 53.3% | 53.3% |
| Revisión | 22.4% | 23.2% |
| Rechazo | 24.3% | 23.5% |
| Aprobación final esperada | 66.7% | 67.2% |
| Default de la cartera final | 10.7% | 10.7% |
| Pérdida esperada / monto | 2.9% | 2.9% |

Las conclusiones de 6.9 no cambian: la política sigue dentro de los límites de riesgo, sigue sin alcanzar el objetivo de aprobación de 70% y sigue exigiendo algo más de capacidad de revisión que la declarada.
