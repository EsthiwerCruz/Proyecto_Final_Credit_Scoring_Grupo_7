# Credit Risk Capstone · Caso 15 · Caja Rural 360

Trabajo Integrador Final de **Credit Risk & Scoring Analytics 2026** (DMC Institute). Caso: **microcrédito rural amortizable y sin garantía** para clientes independientes con ingresos parcialmente en efectivo. El objetivo de la entidad es crecer fuera de agencias sin excluir automáticamente a quien no tiene trazabilidad bancaria.

> Datos 100% sintéticos con fines académicos (`data/raw/`, copia de `Dataset/Caso_15`).

## Avance

Este repositorio contiene **las secciones 6.1 a 6.15** del enunciado, es decir, el alcance técnico completo:

| Sección | Tema | Documento | Notebook |
|---|---|---|---|
| 6.1 | Negocio, ciclo de crédito end-to-end, decisión del modelo, Risk Appetite, supuestos, exclusiones y revisión manual | `reports/01_negocio_y_arquitectura_crediticia.md` | `00_negocio_y_poblacion.ipynb` |
| 6.2 | Target, observation date, performance window, población, sesgos, split temporal y variables disponibles en T0 | `reports/02_definicion_modelo_y_poblacion.md` | `00_negocio_y_poblacion.ipynb` |
| 6.3 | Perfilado de calidad, diccionario técnico, pipeline de faltantes y categóricas, variables derivadas y estabilidad temporal | `reports/03_data_strategy_calidad_features.md` | `01_calidad_y_features.ipynb` |
| 6.4 | EDA orientado a riesgo: señal de las variables, deterioro temporal, capacidad de pago, canales, fairness, exposición y 14 hallazgos accionables | `reports/04_eda_orientado_a_riesgo.md` | `02_eda_riesgo.ipynb` |
| 6.5 | Scorecard tradicional: binning, WOE/IV, selección S1-S7, logística, escala de puntos, bandas y calibración | `reports/05_scorecard_tradicional.md` | `03_scorecard_pd.ipynb` |
| 6.6 | Modelos PD y Champion/Challenger: logística, Random Forest, XGBoost y LightGBM con tuning temporal y veto de fairness | `reports/06_modelos_pd.md` | `04_modelos_pd.ipynb` |
| 6.7 | Validación y calibración: métricas completas en DEV/VAL/OOT, deciles, lift, Platt vs. isotónica y PSI | `reports/07_validacion_calibracion.md` | `05_validacion_calibracion.ipynb` |
| 6.8 | Explainability y fair lending: puntos del scorecard, SHAP, tres clientes explicados, AIR y prueba de proxy | `reports/08_explainability_fairness.md` | `06_explainability_fairness.ipynb` |
| 6.9 | Motor de decisión: cut-off, reglas, contraoferta de monto, pricing por riesgo, swap analysis y rentabilidad | `reports/09_decision_engine.md` | `07_decision_engine.ipynb` |
| 6.10 | EAD: factor de exposición para producto amortizable, coherencia con la amortización, baseline vs. modelos | `reports/10_ead.md` | `08_ead_lgd.ipynb` |
| 6.11 | LGD: descomposición, baseline vs. modelos acotados, LGD económica descontada y downturn | `reports/11_lgd.md` | `08_ead_lgd.ipynb` |
| 6.12 | Expected Loss por cliente y cartera, tablero por segmento, escenarios Base/Adverse/Severe y capital | `reports/12_expected_loss_stress.md` | `09_expected_loss_stress.ipynb` |
| 6.13 | Arquitectura end-to-end, servicio FastAPI con interfaz web, Model Registry con hash, promoción/rollback y disparadores | `reports/13_arquitectura_api_mlops.md` | `10_api_arquitectura.ipynb` |
| 6.14 | Materialidad, ciclo de vida, tres líneas de defensa, Model Card, validación independiente y checklist de auditoría | `reports/14_gobierno_model_risk.md` | `11_gobierno_monitoreo.ipynb` |
| 6.15 | Monitoreo de datos, modelo y negocio con umbrales, acciones y tablero | `reports/15_monitoring.md` | `11_gobierno_monitoreo.ipynb` |

Además, dos documentos consolidados que **se generan** desde los reportes de sección (`python run_all.py --documentos`):

| Documento | Archivo | Qué es |
|---|---|---|
| Anexo de trazabilidad | `reports/16_anexo_trazabilidad.md` | Cada requisito del enunciado, entregable y control del Technical Gate contra el archivo que lo evidencia, **verificando que exista** |
| Documento técnico | `reports/documento_tecnico.md` | Las quince secciones consolidadas con portada, decisiones, supuestos, limitaciones y anexos (unas 75 páginas) |
| Informe ejecutivo | `reports/informe_ejecutivo.md` | Para Gerencia y Comité: recomendación, impacto, caso económico en soles, riesgos y decisiones pedidas |
| Presentación | `reports/presentacion.md` | Contenido de los 10 slides de sustentación; el `.pptx` se genera con `node tools/build_deck.js` |

## Definiciones clave

- **Target:** `default_12m_flag` = 90 o más días de mora en (T0, T0 + 12m], con T0 = `observation_date`.
- **Población PD:** `outcome_available_flag = 1` → 5,783 créditos, 671 defaults (11.60%). Los 1,217 rechazados se excluyen: no son "buenos".
- **Split temporal:** DEV 2021-2023 (10.2%) · VAL 2024 (14.0%) · OOT 2025 (13.4%).
- **Variables prohibidas en PD:** tasa ofrecida (endógena), indicadores de decisión y target, y todos los campos posteriores al default (`data.forbidden_pd_features()`).
- **Tratamiento de datos:** un único pipeline (recálculo de `dti` y variables derivadas → winsorización p1-p99 → imputación por mediana → one-hot) ajustado solo con DEV y aplicable a una solicitud individual (`pipeline.build_pipeline()`). Los faltantes son compatibles con MCAR; los indicadores de faltante se usan en política y monitoreo, no en el modelo.
- **Variables derivadas:** 10 evaluadas con un protocolo decidido solo con DEV (`features.screen_derived_features`); quedan como candidatas `dti_post` y `ahorro_sobre_monto`.
- **Risk Appetite:** 14 métricas con tipo, semáforo, prueba de factibilidad 2021-2024 y regla de precedencia (los límites de riesgo prevalecen sobre el objetivo de aprobación).
- **Scorecard PD (6.5):** buró + DTI post-crédito + ahorro sobre monto. Escala 600 puntos = odds 10:1, PDO 20. Gini 0.440 (DEV), 0.348 (VAL) y 0.424 (OOT).
- **Champion / Challenger (6.6):** champion = scorecard (más simple y mejor fuera de muestra); challenger = LightGBM monótono, con el mismo veto de fairness.
- **PD de producción (6.7):** `Platt(PD del scorecard)`, calibrador ajustado en VAL (intercepto −0.08, pendiente 0.758) y probado en OOT.
- **Severidad (6.10 y 6.11):** factor de exposición 0.415 y LGD contable 0.616, ambos baselines globales estimados con los defaults de DEV; ningún modelo los supera fuera de muestra. La LGD económica (descontada al 10%) es 0.654 y el recargo de downturn, 0.7 pp.
- **Gobierno (6.14):** materialidad Tier 1, Model Card generada desde los artefactos, inventario con hash y validación independiente con 10 hallazgos (2 de severidad alta) y plan de remediación.
- **Monitoreo (6.15):** 13 indicadores de datos, modelo y negocio con umbrales Verde/Ámbar/Rojo y acción asignada; tablero en `reports/dashboard_monitoreo.html`.
- **Expected Loss y stress (6.12):** base económica de LGD con el umbral del apetito restateado a 3.34% verde; cartera 2025 con 2.99% de pérdida esperada; en Severe la política absorbe 1.5 puntos del shock reduciendo sola la aprobación. Tablero en `reports/dashboard_cartera.html`.
- **Servicio de scoring (6.13):** FastAPI con `/score`, `/score/batch`, `/health` y `/version`; 0.18 ms por solicitud en lote y **misma PD, score y decisión que el desarrollo** sobre 200 solicitudes (sin train-serve skew).
- **Política de crédito (6.9):** APPROVE con PD calibrada ≤ 18%, REJECT sobre 20%, contraoferta automática de monto al 45% de DTI post-crédito y revisión manual por cuatro reglas duras. En OOT 2025: 64.6% de aprobación con 9.3% de default esperado, contra 81.6% y 13.4% de la política histórica.

## Estructura

```
credit-risk-capstone/
├── data/
│   ├── raw/                  data.csv, diccionario_datos.csv, README.txt (Caso 15)
│   └── processed/            pd_population.csv y pd_population_features.csv
├── notebooks/
│   ├── 00_negocio_y_poblacion.ipynb   evidencia de 6.1 y 6.2
│   ├── 01_calidad_y_features.ipynb    evidencia de 6.3
│   ├── 02_eda_riesgo.ipynb            evidencia de 6.4
│   ├── 03_scorecard_pd.ipynb          evidencia de 6.5
│   ├── 04_modelos_pd.ipynb            evidencia de 6.6
│   ├── 05_validacion_calibracion.ipynb evidencia de 6.7
│   ├── 06_explainability_fairness.ipynb evidencia de 6.8
│   ├── 07_decision_engine.ipynb       evidencia de 6.9
│   ├── 08_ead_lgd.ipynb               evidencia de 6.10 y 6.11
│   ├── 09_expected_loss_stress.ipynb  evidencia de 6.12
│   ├── 10_api_arquitectura.ipynb      evidencia de 6.13
│   └── 11_gobierno_monitoreo.ipynb    evidencia de 6.14 y 6.15
├── src/
│   ├── config.py             rutas, target, split temporal, parámetros de política
│   ├── data.py               carga, catálogo de variables, población PD, split
│   ├── risk_appetite.py      umbrales, semáforo, tipo de métrica, precedencia y factibilidad
│   ├── validation.py         PSI, AUC con dirección, Mann-Whitney y tests de aporte incremental
│   ├── quality.py            perfilado de calidad, reglas, estacionalidad y mecanismo de faltantes
│   ├── features.py           variables derivadas y su pre-selección (R1-R5, solo DEV)
│   ├── pipeline.py           pipeline de winsorización, imputación y encoding
│   ├── data_dictionary.py    diccionario técnico (tratamiento, leakage, uso final)
│   ├── eda.py                EDA de riesgo: IC de Wilson, FDR, interacción, nivel vs. pendiente, cohortes
│   ├── scorecard.py          binning, WOE/IV, selección S1-S7, logística, puntos y reason codes
│   ├── models.py             candidatos PD, tuning temporal, veto de fairness y Champion/Challenger
│   ├── evaluation.py         métricas de 6.7, deciles, lift/gains, calibración y recalibración
│   ├── fairness.py           AIR, tasas de error por grupo, prueba de proxy y SHAP
│   ├── decision.py           motor de decisión, contraoferta, pricing, trade-off y swap analysis
│   ├── severity.py           EAD y LGD: baselines segmentados, logística fraccional, LGD económica y downturn
│   ├── portfolio.py          Expected Loss, tablero por segmento, capital IRB y motor de escenarios
│   ├── registry.py           Model Registry: inventario, hash, promoción, rollback y disparadores
│   ├── governance.py         materialidad, ciclo de vida, Model Card, hallazgos y checklist de auditoría
│   ├── monitoring.py         indicadores por cosecha, umbrales, semáforos y acciones
│   ├── traceability.py       mapa de requisitos del enunciado y generador del anexo
│   ├── techdoc.py            consolidación de los reportes en el documento técnico
│   ├── execreport.py         informe ejecutivo con las cifras tomadas de los artefactos
│   └── diagrams.py           diagrama del ciclo de crédito
├── api/
│   └── main.py               servicio FastAPI de scoring (uvicorn api.main:app)
├── models/
│   ├── scorecard_pd_v1.json      champion: tramos, WOE, coeficientes y escala
│   ├── calibrador_platt_v1.json  calibración de la PD de producción (6.7)
│   ├── challenger_lgbm_v1.joblib challenger LightGBM monótono (6.6)
│   ├── politica_decision_v1.json umbrales, supuestos económicos y resultados (6.9)
│   ├── ead_lgd_v1.json           parámetros de exposición y severidad (6.10 y 6.11)
│   ├── registry.json             inventario versionado con hash SHA-256 (6.13)
│   ├── model_card_scorecard_pd.md  Model Card del champion, generada desde los artefactos (6.14)
│   └── ficha_ead.md · ficha_lgd.md fichas técnicas de exposición y severidad (6.14)
├── tests/
│   ├── test_data.py          población, split, catálogo, rangos y apetito
│   ├── test_features.py      calidad, faltantes, derivadas, pre-selección y pipeline
│   ├── test_eda.py           IC, FDR, tablas de default, tamizaje y concentración de pérdida
│   ├── test_scorecard.py     binning, WOE, escala, puntos, razones, selección y artefacto
│   ├── test_pd_policy.py     folds temporales, veto, calibración, AIR, proxy y motor de decisión
│   ├── test_severity.py      coherencia de EAD, baselines, modelos acotados, LGD económica y downturn
│   ├── test_portfolio.py     Expected Loss, shocks sobre odds, capital IRB y tablero
│   ├── test_api.py           contrato del servicio, validaciones, consistencia y registro
│   ├── test_governance_monitoring.py  materialidad, hallazgos, Model Card, umbrales y semáforos
│   └── test_despliegue.py    interfaz web, portabilidad, imagen, anexo y documento técnico
├── reports/
│   ├── 01_negocio_y_arquitectura_crediticia.md
│   ├── 02_definicion_modelo_y_poblacion.md
│   ├── 03_data_strategy_calidad_features.md
│   ├── 04_eda_orientado_a_riesgo.md
│   ├── 05_scorecard_tradicional.md
│   ├── 06_modelos_pd.md
│   ├── 07_validacion_calibracion.md
│   ├── 08_explainability_fairness.md
│   ├── 09_decision_engine.md
│   ├── 10_ead.md
│   ├── 11_lgd.md
│   ├── 12_expected_loss_stress.md
│   ├── 13_arquitectura_api_mlops.md
│   ├── 14_gobierno_model_risk.md
│   ├── 15_monitoring.md
│   ├── 16_anexo_trazabilidad.md  generado: requisitos contra evidencia verificada
│   ├── documento_tecnico.md      generado: las 15 secciones consolidadas
│   ├── informe_ejecutivo.md      generado: informe para Gerencia y Comité
│   ├── presentacion.md           contenido de los 10 slides de sustentación
│   ├── independent_validation_report.md  informe de validación independiente (6.14)
│   ├── dashboard_monitoreo.html  tablero de monitoreo (6.15)
│   ├── dashboard_cartera.html  tablero autocontenido de cartera y stress (6.12)
│   ├── revision_6.1_6.3.md     registro de la revisión: hallazgos, evidencia y cambios
│   ├── figures/              fig01-fig35 (PNG)
│   └── tables/               CSV citados en los reportes
└── requirements.txt
```

## Cómo ejecutar

### 1. Preparar el entorno (una sola vez)

Python 3.10 o superior. Desde la raíz del repositorio:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell o CMD)
source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
```

### 2. Correr todo con un comando

```bash
python run_all.py
```

Ejecuta, en este orden: las 107 pruebas automáticas, los doce notebooks (00 → 11), la generación del anexo y del documento técnico, y una verificación final
que comprueba la integridad de los artefactos contra el Model Registry y que el servicio de scoring responde.
Se detiene en el primer error. Toma entre 15 y 25 minutos según la máquina.

Variantes útiles:

```bash
python run_all.py --tests          # solo las pruebas (~30 segundos)
python run_all.py --notebooks      # solo los notebooks
python run_all.py --desde 04       # retomar desde el notebook 04 en adelante
python run_all.py --documentos     # regenerar informe ejecutivo, documento técnico y anexo
python run_all.py --verificar      # solo la verificación de artefactos y servicio
```

### 3. Trabajar notebook por notebook

```bash
jupyter notebook notebooks/00_negocio_y_poblacion.ipynb
```

El orden importa: el 03 deja `models/scorecard_pd_v1.json`, el 04 el challenger, el 05 el calibrador,
el 07 la política y el 08 los parámetros de EAD y LGD. Del 04 en adelante cada notebook necesita lo que
dejó el anterior. Cada uno corre de arriba hacia abajo, desde `notebooks/` o desde la raíz, y regenera
`data/processed/`, `reports/tables/`, `reports/figures/`, `reports/dashboard_cartera.html` y `models/`.

### 4. Levantar el servicio de scoring

```bash
uvicorn api.main:app --reload --port 8000
```

- **Interfaz web para evaluar solicitudes:** <http://localhost:8000/> — formulario con tres ejemplos precargados
  (aprobado, revisión y rechazado), decisión con su badge, score, PD, monto, tasa y razones. Sin dependencias
  externas: funciona sin internet, que es lo que conviene para la demo en vivo de la sustentación.
- Documentación interactiva (OpenAPI): <http://localhost:8000/docs>
- Estado e integridad de artefactos: <http://localhost:8000/health>
- Ejemplos de request y response: `reports/tables/api_ejemplos.json` o el endpoint `/ejemplos`

### 4.1. Con Docker (opcional)

```bash
docker build -t cajarural360-api .
docker run --rm -p 8000:8000 cajarural360-api
```

La imagen solo lleva lo que la API necesita: el scorecard es un JSON, así que no incluye LightGBM, SHAP ni
matplotlib. Corre con usuario sin privilegios y trae `HEALTHCHECK`.

### 4.2. Publicar en Azure (opcional)

No hace falta tener Docker instalado: la imagen se construye en Azure con `az acr build`.

```bash
az login
bash deploy/azure/deploy.sh cajarural360 eastus        # Linux / macOS
.\deploy\azure\deploy.ps1 -Nombre cajarural360        # Windows
```

Levanta Container Registry, Log Analytics y Container Apps con `deploy/azure/main.bicep`, publica la imagen y
devuelve la URL. La app **escala a cero** cuando no hay tráfico, así que sin uso no consume crédito. Para
borrar todo: `az group delete -n cajarural360-rg --yes`.

### 4.3. Subirlo a GitHub

El repositorio pesa **13 MB** sin el entorno virtual. Nunca subas `.venv/`: `xgboost.dll` pesa 177 MB y GitHub
rechaza archivos de más de 100 MB. El `.gitignore` ya lo excluye.

```bash
git init -b main                      # si aún no está inicializado
git add .
git commit -m "TIF Credit Risk & Scoring Analytics - Caso 15"
git remote add origin https://github.com/<usuario>/<repositorio>.git
git push -u origin main
```

Al primer push, GitHub Actions corre la suite de pruebas en Python 3.10 y 3.11 (`.github/workflows/tests.yml`).
El despliegue a Azure es manual desde la pestaña Actions y requiere el secreto `AZURE_CREDENTIALS`.

### 5. Ver los resultados

- **Tablero de cartera y stress:** abrir `reports/dashboard_cartera.html` en cualquier navegador (es autocontenido).
- **Reportes por sección:** `reports/01_...md` a `reports/13_...md`.
- **Tablas y figuras:** `reports/tables/` (80 CSV) y `reports/figures/` (34 PNG).

### Reproducibilidad

Todas las salidas son deterministas (semilla `SEED = 42` en `src/config.py`), con una excepción documentada:
la columna de latencia de `modelos_comparacion.csv`, que mide milisegundos y depende de la máquina.
Si no tienes pytest, las pruebas también corren con `python tests/test_data.py`.
