# Ficha de propuesta inicial del equipo

**Trabajo Integrador Final · Credit Risk & Scoring Analytics 2026 · DMC Institute**
**Equipo:** Credit Risk Analytics (4 integrantes) · **Caso seleccionado:** 15 · Caja Rural 360

---

**1. Caso seleccionado y justificación.** Caso 15, Caja Rural 360: microcrédito rural amortizable, sin garantía, para independientes con ingresos parcialmente en efectivo. Concentra las tensiones centrales: trazabilidad bancaria parcial e inclusión que choca con el límite de riesgo.

**2. Pregunta de negocio.** ¿Hasta dónde puede crecer la Caja fuera de agencias, y con qué política de aprobación, monto y precio, sin superar su límite de pérdida ni excluir a quien no tiene historial bancario formal?

**3. Target y población inicial propuesta.** Target `default_12m_flag`: 90 o más días de mora dentro de los 12 meses posteriores a `observation_date`. Población: solicitudes con resultado observable (`outcome_available_flag = 1`), unas 5,800 de 7,000; **los rechazados no se tratan como buenos**.

**4. Risk Appetite preliminar.** Tres límites y un objetivo, a refinar en 6.1 con umbrales Verde/Ámbar/Rojo:
aprobación sobre solicitudes **≥ 70%** (objetivo de negocio) · default a 12 meses **≤ 11%** y pérdida esperada sobre
monto **≤ 3%** (límites de riesgo) · revisión manual **≤ 20%** de las solicitudes (restricción operativa). Se define desde el inicio una **regla de precedencia**: ante conflicto, prevalece el límite de riesgo y el caso se escala al Comité con el trade-off cuantificado.

**5. Hipótesis principales.**

1. El buró será dominante, pero la capacidad de pago post-crédito aportará señal incremental.
2. El deterioro 2021-2024 puede ser de **población** o de **nivel**: define si se recalibra o se reentrena.
3. Territorio e informalidad: poca señal y alto riesgo de fair lending, **fuera del modelo**.
4. Sin buró o sin ingreso: **verificación**, no rechazo.
5. Exposición y severidad serán estables: la palanca está en la frecuencia.

**6. Esquema temporal preliminar.** Partición **temporal**, no aleatoria, para medir estabilidad entre cosechas:
**Development 2021-2023** (binning, selección de variables y coeficientes) · **Validation 2024** (comparación de modelos
y calibración) · **Out-of-Time 2025**, que se abre **una sola vez** al final para medir desempeño real.

**7. Arquitectura conceptual inicial.** Datamart con foto en T0 y ventana de 12 meses → pipeline ajustado solo con Development → PD calibrada → motor de reglas (PD + capacidad de pago + política) → servicio de scoring con decisión, razones, monto y tasa → registro y monitoreo con semáforos. Entornos separados: Development, Validation, Production y Monitoring.

**8. Riesgos metodológicos que esperamos enfrentar.** **Sesgo de selección** (rechazados sin resultado) · **leakage** de campos post-decisión y post-default, y de la tasa ofrecida, endógena · **drift temporal** que descalibre la PD · **pocos defaults** para EAD y LGD · **proxies de fairness** que entren por modelos complejos.
