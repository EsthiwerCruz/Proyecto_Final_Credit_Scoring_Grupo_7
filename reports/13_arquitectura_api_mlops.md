# 6.13 · Arquitectura, API y MLOps

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/10_api_arquitectura.ipynb`; servicio en `api/main.py`; registro en `src/registry.py` y `models/registry.json`; figura `fig34`; tablas `mlops_*.csv` y `api_*.{csv,json}`.

---

## 1. Resumen

- **Arquitectura lógica end-to-end** documentada en `fig34`: fuentes → ingesta → datamart → feature pipeline → modelo PD → motor de reglas → API → consumo → registro → monitoreo → reentrenamiento.
- **Servicio de scoring funcional en FastAPI** con `/health`, `/version`, `/score` y `/score/batch`. Devuelve el contrato mínimo que pide el enunciado (§16) más motivo, pérdida esperada, versión de modelo y `trace_id`.
- **El servicio no reimplementa nada:** importa los mismos módulos y carga los mismos artefactos versionados que los notebooks. Verificado sobre 200 solicitudes: **PD, score y decisión idénticos**. Sin *train-serve skew*.
- **Model Registry** con versión, estado, dueño y **hash SHA-256** de cada artefacto. `/health` falla si alguien reemplaza un artefacto sin registrar el cambio.
- **Champion/Challenger, promoción y rollback** implementados como operación reversible: el modelo anterior no se borra, se degrada.
- **Ocho disparadores de recalibración y reentrenamiento**, cada uno atado a un número medido en las secciones anteriores.
- **Latencia: 0.18 ms por solicitud** en lote y ~11 ms en la primera llamada individual (incluye validación y serialización).

## 2. Arquitectura lógica

| Capa | Qué hace | Dónde vive en este repo |
|---|---|---|
| Fuentes | Core bancario y CRM, consulta al buró en T0, canales de originación, geocodificación | Insumo externo |
| Ingesta | Cargas batch diarias, eventos de originación, contratos de datos y las 20 reglas de calidad | `src/quality.py` |
| Datamart de riesgo | Snapshot por solicitud en T0, ventana de performance de 12 meses, versionado por fecha de corte | `src/data.py`, `data/processed/` |
| Feature pipeline | Recálculo de `dti`, `dti_post`, `ahorro_sobre_monto` e indicadores; **el mismo objeto en desarrollo y producción** | `src/features.py`, `src/pipeline.py` |
| Modelo PD | Scorecard WOE (champion) + calibrador Platt; challenger LightGBM en sombra | `models/scorecard_pd_v1.json`, `calibrador_platt_v1.json` |
| Motor de reglas | Reglas duras, capacidad de pago, contraoferta de monto, APPROVE/REVIEW/REJECT, pricing | `src/decision.py`, `models/politica_decision_v1.json` |
| API de scoring | Contrato validado, decisión y razones, trazabilidad por solicitud | `api/main.py` |
| Consumo | Originación en canal, cola de revisión del analista, oferta de monto y tasa | Integración del canal |
| Registro y trazabilidad | `trace_id` por decisión, versión de modelo y política, log de inputs | `api/main.py` + `src/registry.py` |
| Monitoreo | PSI, calibración, Gini, EL contra apetito, AIR | 6.12 y 6.15 |
| Reentrenamiento | Recalibración con ventana nueva, reentrenamiento, validación independiente | 6.7 y 6.14 |

**Los entornos son conceptuales y atraviesan todo el flujo.** El mismo pipeline y los mismos artefactos corren en los cuatro; lo que cambia son los datos, los permisos y quién aprueba.

| Entorno | Datos | Quién entra | Qué se puede hacer |
|---|---|---|---|
| **Development** | Histórico hasta el corte de DEV | Equipo de Analytics | Ajustar, experimentar, versionar candidatos |
| **Validation** | VAL y OOT (una sola vez) | Analytics + validador independiente | Comparar modelos, calibrar, firmar la validación |
| **Production** | Solicitudes reales en línea | Solo el servicio (sin escritura humana) | Puntuar y decidir con artefactos promovidos |
| **Monitoring** | Cosechas cerradas y logs de decisión | Riesgos y Auditoría | Vigilar, disparar recalibración, pedir rollback |

## 3. El servicio de scoring

**Contrato de entrada:** las 19 variables que necesita el pipeline, con rangos validados por Pydantic (edad 18-100, score de buró 300-900, plazo 3-60, monto hasta S/ 200,000, participación de efectivo 0-1) más una validación de negocio: la cuota de deudas vigentes no puede superar el ingreso declarado. `bureau_score`, `monthly_income` y `savings_balance` **aceptan nulo**, porque la política resuelve el faltante con revisión, no con rechazo.

**Respuesta** (ejemplo real de la cosecha 2025, solicitud aprobada; request y response completos en `reports/tables/api_ejemplos.json`, solicitud `C15-000060` con buró 661, ingreso S/ 2,703 y monto pedido S/ 4,426):

```json
{
  "application_id": "C15-000060",
  "pd": 0.1255,
  "score": 604,
  "risk_band": "C",
  "decision": "APPROVE",
  "reason_codes": [
    "Score de buró bajo",
    "Ahorro bajo frente al monto solicitado",
    "Carga de deuda post-crédito alta frente al ingreso"
  ],
  "recommended_amount_or_limit": 4425.54,
  "recommended_rate": 0.1892,
  "motivo": "Riesgo y capacidad dentro del apetito",
  "expected_loss": 158.12,
  "modelo": {
    "scorecard": "scorecard_pd_v1",
    "calibrador": "calibrador_platt_v1",
    "politica": "politica_decision_v1",
    "api": "1.0.0"
  },
  "trace_id": "fc280316-6c4d-4406-b919-0a0c8e5c9f33"
}
```

El notebook deja las **tres consultas de ejemplo** que pide el entregable (APPROVE, REVIEW y REJECT) con su request y su response en `reports/tables/api_ejemplos.json`.

**Validación del contrato**, probada en el notebook y en `tests/test_api.py`:

| Caso | Respuesta |
|---|---|
| Score de buró fuera de rango (1200) | 422 · "Input should be less than or equal to 900" |
| Falta el monto solicitado | 422 · "Field required" |
| Cuota de deudas mayor al ingreso | 422 · validación de negocio |
| Plazo fuera del producto (120 meses) | 422 · "Input should be less than or equal to 60" |

**Interfaz web.** Además del contrato JSON, el servicio expone en `/` una **interfaz interactiva** de una sola
página: formulario con las 19 variables, tres ejemplos reales precargados (aprobado, revisión y rechazado) y la
decisión presentada con badge de color, score en escala, PD, monto y tasa recomendados, razones y motivo. No usa
CDNs ni librerías externas, así que funciona sin internet, que es lo que conviene para la demo en vivo de la
sustentación. La lógica sigue siendo la misma: la página solo llama a `POST /score`.

Levantarlo en local:

```bash
uvicorn api.main:app --reload --port 8000
# http://localhost:8000/        interfaz interactiva
# http://localhost:8000/docs    OpenAPI generado automáticamente
```

## 4. Consistencia desarrollo-producción

La prueba que sostiene todo lo demás: para 200 solicitudes de 2025, la API devuelve **exactamente** la misma PD, el mismo score y la misma decisión que calculan los módulos en el notebook.

| Verificación | Resultado |
|---|---|
| PD idéntica | Sí |
| Score idéntico | Sí |
| Decisión idéntica | Sí |
| Solicitudes comparadas | 200 |

No es casualidad de implementación: es consecuencia de dos decisiones de diseño. El servicio **importa `src/`** en lugar de reescribir la lógica, y el scorecard vive en un **JSON auditable** en lugar de un binario opaco, así que lo que corre en producción es literalmente lo que se documentó en 6.5.

**Latencia:** 0.18 ms por solicitud en lote de 200 y ~11 ms en la primera llamada individual. El presupuesto del canal (respuesta en minutos) queda holgado; el cuello de botella de la originación no será el scoring.

## 5. Model Registry, versionado y rollback

`models/registry.json` guarda por artefacto: nombre, archivo, versión, estado, sección de origen, dueño, muestra de entrenamiento, fecha de registro, tamaño y **SHA-256**.

| Artefacto | Versión | Estado | Sección |
|---|---|---|---|
| `scorecard_pd_v1.json` | 1.0 | **champion** | 6.5 |
| `challenger_lgbm_v1.joblib` | 1.0 | challenger | 6.6 |
| `calibrador_platt_v1.json` | 1.0 | soporte | 6.7 |
| `politica_decision_v1.json` | 1.0 | soporte | 6.9 |
| `ead_lgd_v1.json` | 1.0 | soporte | 6.10 y 6.11 |

- **Integridad:** `GET /health` recalcula el hash de cada archivo y lo compara con el registrado. Si alguien reemplaza un artefacto sin registrar el cambio, el servicio lo reporta. Es el control mínimo que pedirá una validación independiente.
- **Promoción y rollback:** `registry.promote(nombre)` asciende un challenger y degrada al champion anterior a challenger. El rollback es la misma operación en sentido inverso; **el modelo anterior nunca se borra**. El notebook lo demuestra sobre una copia del registro.
- **Versionado de datos:** el datamart se versiona por fecha de corte y la partición temporal está fija en `config.TEMPORAL_SPLITS`, así que cualquier reentrenamiento futuro es reproducible y comparable.

## 6. Disparadores de recalibración y reentrenamiento

Cada disparador sale de un número medido antes, no de una convención genérica (`mlops_disparadores.csv`):

| Dimensión | Disparador | Acción | Origen |
|---|---|---|---|
| Calibración | Observado/predicho de la cosecha fuera de [0.85, 1.15] dos meses seguidos | Recalibrar Platt con la ventana más reciente | 6.7 |
| Calibración | Pérdida esperada de la cosecha por encima de 3.34% | Revisar calibración **antes** que el punto de corte | 6.12 |
| Discriminación | Gini de la cosecha por debajo de 0.30 (piso de la banda histórica 0.35-0.49) | Investigar; si persiste dos cosechas, reentrenar | 6.7 |
| Estabilidad | PSI del score sobre 0.10 o de una variable sobre 0.25 | Investigar el cambio de mezcla; reentrenar si es estructural | 6.7 |
| Población | Faltantes de buró o ingreso al doble de lo histórico | Revisar la fuente antes de tocar el modelo | 6.3 |
| Severidad | LGD o factor de exposición fuera de ±5 pp de lo estimado | Reestimar EAD y LGD y actualizar la capa de EL | 6.10 y 6.11 |
| Fairness | AIR por región o por efectivo bajo 0.80 dos meses seguidos | Revisar la política de verificación; escalar al Comité | 6.8 |
| Negocio | Cola de revisión manual sobre 20% de las solicitudes | Priorizar por valor esperado y evaluar capacidad | 6.9 |

El orden importa: **primero calibración, después corte, y solo al final reentrenamiento**. La evidencia de 6.4 y 6.7 dice que en esta cartera el problema suele ser de nivel y no de ordenamiento, y reentrenar cuando el problema es de calibración cambia el modelo sin resolver nada.

## 7. Ruta de despliegue en la nube

El despliegue real es opcional en el enunciado. Aquí no solo se define la ruta: se entrega **la infraestructura
como código y los scripts listos para ejecutar**.

| Entregable | Archivo | Qué hace |
|---|---|---|
| Imagen | `Dockerfile` + `requirements-api.txt` | Imagen mínima (sin LightGBM, SHAP ni matplotlib), usuario sin privilegios y `HEALTHCHECK` |
| Infraestructura | `deploy/azure/main.bicep` | Container Registry, Log Analytics y Container App con sondas a `/health` y escala a cero |
| Despliegue | `deploy/azure/deploy.sh` y `deploy.ps1` | Crea todo y publica con `az acr build`, **sin Docker local** |
| Integración continua | `.github/workflows/tests.yml` | Corre la suite en Python 3.10 y 3.11 en cada push |
| Despliegue continuo | `.github/workflows/deploy-azure.yml` | Despliegue **manual**, porque promover es un acto de gobierno (6.14) |

Mapa de servicios:

| Componente | Servicio | Nota |
|---|---|---|
| Datamart | Azure Data Lake + Synapse | Particionado por fecha de corte; el snapshot en T0 es inmutable |
| Feature pipeline y entrenamiento | Azure Machine Learning (jobs programados) | Reutiliza `src/` sin cambios; semilla y versiones fijadas en `requirements.txt` |
| Registro de modelos | Azure ML Model Registry | `models/registry.json` es el equivalente local y su formato mapea 1 a 1 |
| Servicio de scoring | Azure Container Apps o App Service (contenedor con la misma imagen que corre en local) | Escala horizontal; sin estado |
| Secretos y credenciales | Azure Key Vault | La API no guarda credenciales en el repo |
| Observabilidad | Application Insights + tablero de 6.12 y 6.15 | `trace_id` y versión de modelo en cada log |
| Orquestación | Azure Data Factory o Airflow | Cargas diarias, monitoreo mensual, recalibración trimestral |

**Trazabilidad y seguridad.** Cada respuesta lleva `trace_id`, versión de modelo, de calibrador, de política y de API, de modo que cualquier decisión puede reconstruirse meses después. Los inputs se registran en un log inmutable para poder recalcular la decisión con el mismo código y el mismo artefacto. En producción la API es de solo lectura sobre los artefactos: **ningún proceso en línea reescribe un modelo**; solo la promoción registrada puede cambiar el champion.

## 8. Limitaciones

1. **No hay despliegue real ni pruebas de carga**: la latencia se midió en proceso, no bajo concurrencia ni con red de por medio.
2. **El challenger no corre en sombra en la API**: está registrado y versionado, pero el scoring en línea es solo del champion, para no duplicar latencia y dependencias. Si se quiere sombra real, es un endpoint adicional y un log paralelo.
3. **La autenticación no está implementada** (el enunciado no la exige). En producción corresponde API key o OAuth2 por canal, con límites de tasa por consumidor.
4. **El registro es un archivo JSON**: suficiente y auditable para este alcance, pero en producción debería moverse al registro de la nube, con control de acceso y bitácora de cambios.

## 9. Trazabilidad del requisito 6.13

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Arquitectura lógica end-to-end con datos, procesamiento, feature pipeline, modelo, reglas, API, registro, monitoreo y trazabilidad | §2 · `fig34` |
| Servicio básico de scoring en Python, preferentemente FastAPI, con endpoint funcional y ejemplo de request/response | §3 · `api/main.py` · `api_ejemplos.json` |
| Separar entornos Development, Validation, Production y Monitoring | §2 |
| Versionado de datos/modelo, Model Registry, rollback y Champion/Challenger | §5 · `src/registry.py` · `models/registry.json` |
| Triggers de recalibración y reentrenamiento | §6 · `mlops_disparadores.csv` |
| Indicar cómo se llevaría a Azure u otra nube | §7 |
