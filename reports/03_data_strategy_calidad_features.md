# 6.3 Data Strategy, calidad y feature engineering

**Caso 15 · Caja Rural 360 · Microcrédito rural para independientes**

> **Evidencia:** `notebooks/01_calidad_y_features.ipynb`; tablas en `reports/tables/` (prefijos `calidad_`, `faltantes_`, `features_`, `diccionario_`) y figuras `fig08` a `fig10`. El código vive en `src/quality.py`, `src/features.py`, `src/pipeline.py` y `src/data_dictionary.py`, y `tests/test_features.py` verifica las reglas. Parte de la población PD y del catálogo de variables definidos en 6.2.

---

## 1. Resumen

- **La base está limpia en lo estructural.** Sin duplicados de ningún tipo, sin valores imposibles y con solo tres variables con faltantes, ninguna por encima del 8%. De 20 reglas de consistencia y lógica de negocio, 15 se cumplen sin excepción. El hallazgo con más consecuencias es que el archivo trae `dti` incluso cuando falta el ingreso (145 créditos), algo imposible en producción: el pipeline lo corrige recalculando `dti` desde sus insumos.
- **Los faltantes son compatibles con MCAR.** Ninguno se puede predecir con las demás variables de la solicitud (AUC con validación cruzada 0.50-0.51) ni cambia por año o con la aprobación. Ingreso y ahorro no se relacionan con el default. Quien no tiene score **sí** tiene historial de buró, así que no es thin-file, y su menor default de 2021-2022 desaparece en 2023. Se imputan con la mediana de DEV y los indicadores se reservan para la política y el monitoreo.
- **El problema no es la calidad del dato, es la cola.** `savings_balance` llega a S/ 243,909 con una mediana de S/ 2,667 (asimetría 11.2). Se resuelve acotando a p1-p99 dentro del pipeline, sin eliminar registros.
- **Las variables son estables; el target no.** El PSI máximo entre DEV y OOT es 0.017, muy por debajo del umbral de 0.10, mientras el default sube de 8.6% a 13.4%. Confirma, ahora con métricas de calidad, que el deterioro es del entorno y no de la población que solicita.
- **Se evaluaron 10 variables derivadas con un protocolo decidido solo con DEV:** señal con dirección, estabilidad del signo, aporte sobre sus componentes, necesidad de negocio si usan una variable sensible y redundancia. Se conservan **2 candidatas**: `dti_post`, que es intercambiable con `dti` como predictor pero preferible porque reacciona al monto y plazo que se deciden, y `ahorro_sobre_monto`. Se descartan 8 con evidencia, entre ellas la estacional y la que castigaba por construcción el ingreso en efectivo.
- **Todo el tratamiento vive en un solo objeto** de scikit-learn, ajustado únicamente con DEV y capaz de puntuar una solicitud individual, que es como lo usará el servicio de scoring.

---

## 2. Perfilado de calidad

### 2.1 Completitud

| Variable | DEV | VAL | OOT | Total | Mecanismo (ver abajo) |
|---|---|---|---|---|---|
| `savings_balance` | 7.4% | 7.8% | 8.5% | 7.7% | Compatible con MCAR; no informativo del riesgo |
| `bureau_score` | 3.7% | 3.1% | 2.6% | 3.3% | Compatible con MCAR; score no disponible (no thin-file) |
| `monthly_income` | 2.5% | 2.4% | 2.8% | 2.5% | Compatible con MCAR; no informativo del riesgo |

Las otras 17 variables candidatas no tienen ningún faltante. Lo relevante para producción es que **la tasa de faltantes es estable entre muestras**: la regla de imputación ajustada en DEV sigue siendo válida en las cosechas siguientes, y una subida repentina de estos porcentajes sería una alerta de monitoreo de datos.

#### Mecanismo de los faltantes

Antes de tratar un faltante hay que saber por qué falta: si depende de otras variables (MAR) o del propio riesgo, imputar sin más sesga el modelo; si es aleatorio (MCAR), basta con imputar (`quality.missingness_report`, `tables/faltantes_mecanismo.csv`).

| Prueba | `monthly_income` | `bureau_score` | `savings_balance` |
|---|---|---|---|
| ¿Cambia la tasa por año? (chi², solicitudes) | No (p = 0.52) | No (p = 0.15) | No (p = 0.65) |
| ¿Se relaciona con la aprobación histórica? | No (p = 0.41) | No (p = 0.54) | No (p = 1.00) |
| ¿Lo predicen las otras 26 variables de T0? (logit, test de razón de verosimilitud) | No (p = 0.54) | No (p = 0.38) | No (p = 0.34) |
| AUC con validación cruzada de ese logit | 0.50 | 0.51 | 0.51 |
| Default con / sin faltante en DEV | 8.2% / 10.2% | 4.8% / 10.4% | 9.0% / 10.3% |
| ¿Informativo controlando por el núcleo de riesgo? (DEV) | No (p = 0.70) | Sí (p = 0.02), pero... | No (p = 0.31) |
| Default con / sin faltante en 2021-2022 y en 2023 | 7.6% / 9.2% · 10.5% / 12.4% | **1.2% / 9.5% · 12.5% / 12.4%** | 8.1% / 9.2% · 10.8% / 12.5% |
| **Conclusión** | MCAR, no informativo | MCAR, efecto inestable | MCAR, no informativo |

**¿Quien no tiene score es thin-file?** No. Estas solicitudes tienen el mismo historial de buró que el resto: 2.0 deudas activas en promedio (88.6% con al menos una), 43.2% con mora previa y el mismo número de consultas; ninguna distribución difiere (KS con p > 0.5; `tables/faltantes_historial_buro.csv`). El buró sí las conoce: lo que no está disponible es el score.

**Tratamiento.** Imputación con la mediana de DEV, que para el score equivale a riesgo neutral. Los indicadores de faltante se calculan, pero **no entran al modelo**: con faltantes MCAR no aportan, y en el buró darle un peso propio trasladaría a producción un efecto concentrado en 2021-2022 (1 default en 86 solicitudes) que en 2023 ya no existe. Se usan en la política (re-consultar el buró, verificar el ingreso) y en el monitoreo de calidad de datos. En el scorecard de 6.5 los bins de faltante deben recibir WOE neutral.

### 2.2 Duplicidad

| Control | Registros |
|---|---|
| Identificador duplicado (`application_id`) | 0 |
| Fila idéntica en todas las columnas | 0 |
| Clave de negocio duplicada (fecha + perfil + monto) | 0 |

No se requiere deduplicación. El control por clave de negocio es el que importa en producción: detecta la misma solicitud reingresada por otro canal, un patrón típico de fraude o de doble captura.

### 2.3 Consistencia y lógica de negocio

De 20 reglas evaluadas sobre la población PD, **15 se cumplen sin excepción**. Los 5 hallazgos:

| Hallazgo | Casos | Severidad | Tratamiento |
|---|---|---|---|
| `relationship_months` mayor a la edad adulta posible | 160 (2.8%) | Baja | Se conservan: es plausible una cuenta de ahorros abierta antes de los 18 años. Se reporta al equipo de captura |
| `dti` informado con ingreso faltante | 145 (2.5%) | Media | Imposible en producción (dti = cuota / ingreso). El pipeline **recalcula `dti` desde sus insumos**: sin ingreso queda faltante y se imputa, como lo haría el servicio de scoring |
| Ingreso menor a la referencia de S/ 1,025 | 103 (1.8%) | Informativa | Se conservan: en el segmento rural informal es plausible, no es un error |
| Antigüedad laboral mayor a la vida laboral posible | 81 (1.4%) | Media | Se conserva el registro; la winsorización limita el extremo y se reporta al equipo de captura |
| Cuota estimada mayor al ingreso mensual | 1 | Alta | La solicitud es inviable por capacidad; la regla de DTI de 6.1 la deriva a revisión manual |

Dos resultados son especialmente importantes para el Technical Gate del enunciado:

1. **No hay contaminación post-evento dentro de la población:** todo crédito con `default = 0` tiene los campos post-default vacíos y todo `default = 1` los tiene informados, sin excepción.
2. **Las variables derivadas del propio archivo cuadran con sus insumos:** `dti` reproduce exactamente `monthly_debt_payment / monthly_income` en todas las filas con ingreso, y `new_customer_flag` es coherente con `relationship_months` en el 100% de los casos. La excepción es la del cuadro: en las 145 filas sin ingreso el `dti` no debería existir. Usarlo sería entrenar con un dato que el modelo no tendrá en producción, por eso se recalcula.

### 2.4 Rangos y outliers

Ninguna variable tiene valores imposibles: todos los mínimos y máximos son plausibles para el producto. Lo que hay son colas largas propias de una cartera de microcrédito:

| Variable | Mediana | p99 | Máximo | Asimetría | Outliers (Tukey k=3) |
|---|---|---|---|---|---|
| `savings_balance` | S/ 2,667 | S/ 29,200 | S/ 243,909 | 11.2 | 176 (3.3%) |
| `distance_to_branch_km` | 9.0 | 55.5 | 150.0 | 3.2 | 123 (2.1%) |
| `monthly_debt_payment` | S/ 862 | S/ 5,159 | S/ 21,396 | 3.2 | 78 (1.4%) |
| `requested_amount` | S/ 6,314 | S/ 29,992 | S/ 78,915 | 2.7 | 74 (1.3%) |

**Decisión: winsorizar, no eliminar.** Son clientes reales del producto y borrarlos sesgaría la PD justo en los perfiles de mayor exposición. Se acotan a p1-p99 con topes ajustados en DEV, de modo que un valor extremo no domine el ajuste de un modelo lineal pero el registro conserve su información de riesgo (`fig08`).

### 2.5 Cardinalidad

Las tres variables categóricas tienen entre 4 y 5 niveles y **ninguna categoría baja del 7%** de la población: no hace falta agrupar categorías raras y un one-hot simple es suficiente, manteniendo la interpretabilidad que el caso exige.

Entre las numéricas, cinco son prácticamente continuas (más del 90% de valores únicos: `cash_income_share`, `requested_amount`, `monthly_debt_payment`, `monthly_income`, `savings_balance`) y cuatro son discretas con pocos niveles y colas ralas (`prior_delinquencies_24m`, `bureau_inquiries_6m`, `active_loans`, `household_dependents`), donde los valores altos no llegan al 5% y deberán agruparse al construir el scorecard.

### 2.6 Estabilidad temporal

| Qué se midió | Resultado |
|---|---|
| PSI de las 20 variables candidatas entre DEV y OOT | Máximo 0.017 (`age`); **ninguna** supera el umbral de alerta de 0.10 |
| PSI entre DEV y VAL | Máximo 0.020 (`employment_tenure_months`) |
| Tasa de default por año de originación | 8.6% → 9.7% → 12.4% → 14.0% → 13.4% (+27.7% en 2023, +13.1% en 2024) |

**La población que solicita no cambió; el riesgo sí** (`fig09`). Para el modelamiento esto tiene dos consecuencias concretas: no hace falta re-ajustar transformaciones ni imputaciones por drift de variables, pero sí habrá que recalibrar el nivel de PD, porque el mismo perfil de cliente incumple más que antes.

---

## 3. Variables derivadas

Todas se calculan solo con insumos de T0 y sin estadísticos de la muestra, para que el mismo código funcione igual en desarrollo y en producción. La cuota del crédito se estima con la **TEA de referencia del producto (30%)** y no con `annual_interest_rate_offer`, que está excluida por endógena (6.2).

### 3.1 Lo que construye el pipeline

| Variable | Fórmula | Racional de negocio | Uso |
|---|---|---|---|
| `dti` (recalculado) | `monthly_debt_payment / monthly_income` | Mismo valor que el archivo cuando hay ingreso; faltante cuando no lo hay, como en producción | Candidata original |
| `cuota_estimada` | `monto × r / (1 − (1+r)^−plazo)`, con `r = (1+TEA_ref)^(1/12) − 1` | Cuota mensual del crédito solicitado; insumo de la capacidad de pago | Insumo |
| `dti_post` | `(monthly_debt_payment + cuota_estimada) / monthly_income` | Carga total si se aprueba. Como predictor es intercambiable con `dti`; se prefiere porque la PD reacciona si se contraoferta monto o plazo, y es la medida de la regla de capacidad | **Candidata** y regla de política |
| `ahorro_sobre_monto` | `savings_balance / requested_amount` | Colchón de ahorro frente al tamaño del crédito pedido | **Candidata** |
| `flag_sin_buro` | 1 si `bureau_score` es nulo | Score no disponible (no thin-file) | Política (re-consulta) y monitoreo |
| `flag_sin_ingreso` | 1 si `monthly_income` es nulo | Sin ingreso no hay capacidad calculable | Política (verificación) y monitoreo |
| `flag_sin_ahorro` | 1 si `savings_balance` es nulo | Faltante MCAR | Monitoreo de calidad |

### 3.2 Pre-selección: qué derivadas aportan

**Por qué se cambió la evaluación.** La versión anterior medía el AUC univariado "orientado al riesgo", es decir max(AUC, 1 − AUC). Ese valor pierde la dirección de la relación y está sesgado hacia arriba: una variable de puro ruido ya marca **0.513 en DEV y 0.519 en VAL** en promedio (1,000 simulaciones), así que los valores de 0.50-0.515 que se reportaban como "señal marginal" eran cero. Además escondía cambios de signo entre muestras. Ahora se usa el AUC con dirección, su p-valor (Mann-Whitney) y el aporte incremental.

**Protocolo** (`features.screen_derived_features`). Se decide **solo con DEV**; VAL se muestra como información y el OOT no se consulta, como fija 6.2. Una derivada se conserva si cumple las cinco reglas:

| Regla | Criterio |
|---|---|
| R1 | Tiene señal en DEV con el signo esperado (Mann-Whitney, p < 0.05) |
| R2 | Mantiene el signo esperado en 2021-2022 y en 2023 (no se invierte dentro de DEV) |
| R3 | Aporta sobre el núcleo de riesgo (buró + dti) y sobre sus propios componentes (test de razón de verosimilitud, p < 0.10: umbral permisivo porque la selección final es en 6.5) |
| R4 | Si usa una variable sensible, esta aporta sobre la versión de la medida sin ella (p < 0.05): prueba de necesidad de negocio |
| R5 | No es redundante (Spearman > 0.70) con otra derivada que pasa R1-R4; se queda la de más señal |

**Resultado** (`tables/features_evaluacion.csv`, `fig10`):

| Derivada | AUC DEV | p DEV | AUC 2021-22 / 2023 | p aporte sobre componentes | Decisión |
|---|---|---|---|---|---|
| `dti_post` | 0.570 | < 0.001 | 0.580 / 0.557 | 0.087 | **Conservada** (intercambiable con `dti`: 6.5 elige una) |
| `ahorro_sobre_monto` | 0.460 | 0.017 | 0.486 / 0.418 | 0.085 | **Conservada** |
| `colchon_ahorro_meses` | 0.463 | 0.028 | 0.485 / 0.429 | 0.091 | Descartada (R5: repite a `ahorro_sobre_monto`, Spearman 0.83) |
| `deuda_por_obligacion` | 0.544 | 0.006 | 0.567 / 0.509 | 0.519 | Descartada (R3: su señal es la de `monthly_debt_payment`) |
| `dti_post_verificable` | 0.548 | 0.004 | 0.550 / 0.545 | 0.255 | Descartada (R3 y R4) |
| `excedente_per_capita` | 0.463 | 0.026 | 0.447 / 0.487 | 0.943 | Descartada (R3 y R4) |
| `antiguedad_relativa` | 0.485 | 0.362 | 0.501 / 0.460 | 0.726 | Descartada (R1-R4) |
| `intensidad_busqueda` | 0.514 | 0.385 | 0.537 / 0.479 | 0.249 | Descartada (R1-R3) |
| `campana_siembra` | 0.489 | 0.389 | 0.485 / 0.493 | 0.286 | Descartada (R1-R3: signo contrario al esperado) |
| `loan_to_income` | 0.501 | 0.935 | 0.487 / 0.521 | 0.162 | Descartada (R1-R3) |

Lectura de las decisiones que más se discutirán:

- **`dti_post` no agrega información estadística a `dti`: son intercambiables** (Spearman 0.83). En un logit lineal con buró, agregar `dti_post` sobre `dti` no aporta (p = 0.61) y a la inversa sí algo (p = 0.02); pero por tramos, que es como trabaja un scorecard, ninguna aporta sobre la otra (p = 0.22 y 0.21), y en VAL tampoco (p = 0.51 y 0.94). Se conserva `dti_post` por dos razones de negocio: incorpora la cuota del crédito que se decide, así la PD reacciona si se contraoferta monto o plazo, y es la misma medida de la regla de capacidad de pago. El scorecard de 6.5 usa **una** de las dos, no ambas.
- **`dti_post_verificable` se descarta aunque tenga AUC 0.548.** Toda su señal viene de `dti_post`: no agrega nada sobre ella (p = 0.23). Además divide por la parte no en efectivo del ingreso, así que castiga por construcción al cliente informal, justo lo contrario del objetivo del caso. El efecto del efectivo sobre el default es débil e inestable (en DEV: 11.3% vs 10.0% sobre 80% de efectivo, p = 0.34; en 2024: 20.3% vs 12.6%). Por eso se atiende con un disparador transparente de **verificación de ingreso** en la política (6.1 §8), no como penalidad dentro del modelo.
- **`campana_siembra` no tiene sustento.** El default no depende del mes de originación (chi² p = 0.89) y en DEV la campaña agrícola tiene incluso menos default. La estacionalidad no es un análisis estándar del scoring de originación y aquí tampoco aporta.
- **`excedente_per_capita`** divide por el tamaño del hogar sin que eso agregue información (p = 0.97 frente al excedente sin dividir): mete una variable sensible sin necesidad de negocio.

### 3.3 Descartadas

Las 8 anteriores quedan documentadas con su fórmula y motivo en `features.discarded_doc`, junto con 2 descartadas en la versión previa: `monto_vs_mediana_region` (AUC 0.501 e introduce un estadístico de muestra) y `mes_originacion` (sin estacionalidad). Documentarlas importa tanto como documentar las que quedaron: muestra que la selección se hizo midiendo, con reglas fijadas antes de mirar los resultados.

---

## 4. Pipeline reproducible

Un único objeto de scikit-learn encadena todo lo que "aprende" del dato:

```
Pipeline
├── FeatureBuilder            recalcula dti y construye cuota, dti_post, ahorro_sobre_monto e indicadores
└── ColumnTransformer
    ├── numéricas (19)        Winsorizer(p1, p99) → SimpleImputer(mediana) → StandardScaler
    └── categóricas (3)       SimpleImputer(moda) → OneHotEncoder(handle_unknown="ignore")
```

**Se ajusta solo con DEV** y se aplica igual a VAL, OOT y a cualquier solicitud nueva. Entra con un esquema fijo de 19 columnas (las candidatas de 6.2 sin `dti`, que se recalcula) y sale con una matriz de 32 columnas. Los indicadores de faltante y las derivadas descartadas no forman parte de la matriz.

| Control | Resultado |
|---|---|
| Mismas columnas en DEV, VAL y OOT | Sí (32 en las tres) |
| Faltantes tras el pipeline | 0 en las tres muestras |
| Topes aprendidos en DEV y aplicados sin recalcular | El máximo de ahorros en OOT (S/ 66,016) queda acotado al tope de DEV (S/ 29,889) |
| Variables prohibidas en la matriz final | Ninguna |
| Indicadores de faltante y derivadas descartadas en la matriz | Ninguno |
| Sin ingreso no hay `dti` | Las 85 filas de DEV sin ingreso quedan sin `dti` antes de imputar |
| Puntuar una solicitud individual | Funciona: entra 1 fila, sale 1 × 32 |

Los dos últimos controles son los que evitan los errores más caros: que una variable de leakage entre por descuido, y que el preprocesamiento de producción difiera del de entrenamiento. Al estar todo en un solo objeto, el servicio de scoring no reimplementa nada.

**Por qué estas decisiones y no otras:**
- **Mediana y no media** para imputar: las variables tienen colas largas y la media quedaría arrastrada por los extremos.
- **Imputar sin indicador dentro del modelo:** los faltantes son compatibles con MCAR, así que el indicador no aporta, y en el buró trasladaría a producción un efecto de 2021-2022 que ya no se observa. Los indicadores se calculan igual para la política y el monitoreo.
- **Recalcular `dti` en lugar de leerlo del archivo:** el servicio de scoring no puede recibir un DTI sin ingreso, así que el entrenamiento tampoco debe verlo.
- **Winsorizar y no eliminar:** eliminar sesgaría la población hacia los clientes promedio.
- **One-hot y no target encoding:** con 4-5 niveles bien poblados no hace falta, y el target encoding introduciría riesgo de leakage y una dependencia del target que complica la explicación ante el Comité.
- **Estandarizar** es opcional (`build_pipeline(scale=False)`): sirve para la regresión logística y es indiferente para los modelos de árboles.

---

## 5. Data Dictionary técnico

`reports/tables/diccionario_tecnico.csv` documenta **55 variables** (41 originales del dataset, 6 derivadas en uso y 8 derivadas evaluadas y descartadas) con las columnas que pide el enunciado:

| Columna | Contenido |
|---|---|
| `origen`, `rol`, `fuente`, `momento`, `disponible_T0` | Heredado del catálogo de 6.2 |
| `transformacion` | Winsorización, fórmula de la derivada o "no se transforma" |
| `imputacion` | Mediana o moda de DEV, con indicador de faltante cuando corresponde |
| `encoding` | One-hot para categóricas; no aplica en numéricas |
| `riesgo_leakage` | De "bajo" a "crítico", con el motivo (por ejemplo, `bureau_inquiries_6m` debe excluir la consulta de la propia solicitud) |
| `uso_final` | Modelo PD, modelo con revisión de fairness, solo pricing, filtro, target o descartada |

Vale la pena destacar tres entradas por su riesgo de leakage:

- **`annual_interest_rate_offer` (alto):** incorpora la evaluación de riesgo anterior. Solo pricing.
- **`bureau_inquiries_6m` (medio):** válida únicamente si el conteo excluye la consulta que genera esta misma solicitud.
- **`monthly_income` (medio, pero de otro tipo):** el riesgo no es temporal sino de manipulación, porque es declarado y poco verificable en un segmento con 60% de ingreso en efectivo.

---

## 6. Implicancias para el scorecard (6.5)

- Capacidad de pago: usar **`dti_post` o `dti`, no ambas** (miden lo mismo).
- Ahorro: usar **`ahorro_sobre_monto` o `savings_balance`, no ambas**.
- Bins de faltante (score, ingreso, ahorro): **WOE neutral**, porque los faltantes son MCAR y el efecto del score faltante no es estable.
- Mantener la regla de decidir con DEV y dejar VAL para comparar modelos y calibrar.

---

## 7. Trazabilidad del requisito 6.3

| Requisito del enunciado | Dónde se evidencia |
|---|---|
| Perfilado de calidad: completitud, duplicidad, consistencia, rangos, outliers, cardinalidad, estabilidad y lógica de negocio | §2 · notebook §2-§7 · `src/quality.py` · tablas `calidad_*.csv` |
| Data Dictionary técnico (transformación, imputación, encoding, leakage, uso final) | §5 · notebook §10 · `src/data_dictionary.py` · `diccionario_tecnico.csv` |
| Pipeline reproducible de faltantes y categóricas | §2.1 (mecanismo de faltantes) y §4 · notebook §2 y §9 · `src/quality.py::missingness_report` · `src/pipeline.py` |
| Variables derivadas con racional y fórmula | §3 · notebook §8 · `src/features.py` (`screen_derived_features`) · `features_derivadas_doc.csv`, `features_evaluacion.csv` |
| Estabilidad temporal de variables y del target | §2.6 · notebook §7 · `fig09` · `calidad_estabilidad_psi.csv` |
| Pruebas | `tests/test_features.py` |
