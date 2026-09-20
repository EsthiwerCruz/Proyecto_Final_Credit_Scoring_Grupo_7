# Presentación ejecutiva · Caso 15 · Caja Rural 360

*Contenido fuente de los 10 slides de sustentación. El archivo `.pptx` se genera a partir de este documento;
si hay que corregir una cifra, se corrige aquí y en el reporte de la sección correspondiente.*

**Criterio:** la presentación no repite el documento técnico. Prioriza **decisión y defensa**: qué se decidió, con qué
evidencia y qué se le pide al Comité. Cada cifra que aparece está respaldada por una tabla del repositorio.

---

## Slide 1 · Portada

**Sistema de scoring y política de crédito**
Caso 15 · Caja Rural 360 · Microcrédito rural amortizable sin garantía

Equipo de Credit Risk Analytics · Credit Risk & Scoring Analytics 2026

*Notas:* presentarse, decir de entrada la recomendación: aprobación automática con PD calibrada hasta 18%, y el
resultado: 64.6% de aprobación con 9.3% de default esperado en la cosecha de prueba.

---

## Slide 2 · El encargo y el conflicto

**Lo que pide el negocio:** crecer fuera de agencias sin excluir a quien no tiene trazabilidad bancaria.

**Lo que fija el apetito:** aprobación ≥ 70% · default ≤ 11% · pérdida esperada ≤ 3%.

**El conflicto es real y está medido:** con el nivel de riesgo de 2024-2025 **no existe** un punto de corte que cumpla a
la vez el objetivo de aprobación y el límite de default. La política propuesta llega a 67.2% de aprobación con 10.7% de
default. Aplica la regla de precedencia escrita en el apetito: **prevalece el límite de riesgo**.

*Notas:* este es el mensaje que diferencia el trabajo. No se disimula moviendo el corte; se cuantifica y se escala.

---

## Slide 3 · Qué encontramos en los datos

| Hallazgo | Evidencia |
|---|---|
| El default subió 5.4 puntos entre 2021 y 2024 | 8.6% → 14.0% |
| **No cambió la población, cambió el riesgo** | PSI del score 0.005; ninguna variable sobre 0.01 |
| **La pérdida creció por frecuencia, no por severidad** | LGD estable en 61.5%-63.4% entre cosechas |

**Consecuencia:** la calibración deja de ser un paso de cierre y pasa a ser un control permanente. Sin recalibrar, el
sistema subestima el riesgo cerca de 30%.

*Notas:* si preguntan por qué no se reentrena, responder: el problema es de nivel, no de ordenamiento.

---

## Slide 4 · El modelo: gana el más simple

| | Scorecard (champion) | Boosting |
|---|---|---|
| Gini fuera de muestra | **0.348** | 0.304 a 0.320 |
| Brecha ajuste vs realidad | 9 puntos | hasta 45 puntos |
| Tiempo por 1,000 solicitudes | < 1 ms | 20 a 40 ms |
| Explicación al cliente | exacta, por puntos | aproximada |

**Desempeño estable:** Gini 0.440 en desarrollo, 0.348 en validación y **0.424 en 2025**, cosecha que nunca se usó para
construirlo.

**Tres características:** score de buró (64% del puntaje), capacidad de pago post-crédito (20%) y ahorro sobre monto (16%).

*Notas:* la regla de selección se fijó antes de ver resultados: gana el más simple que no sea significativamente peor.

---

## Slide 5 · Equidad: lo que medimos y lo que hay que gestionar

**El score no es un proxy.** Con los insumos del modelo no se puede reconstruir la región (acierto igual al azar) ni la
informalidad del ingreso, la distancia, la edad ni los dependientes (R² ≈ 0).

**El punto a gestionar:** el quintil de mayor ingreso en efectivo recibe aprobación automática con un AIR de **0.74**,
bajo el umbral de 0.80. Se repite en 2025, así que no es ruido.

**Por qué ocurre y qué se hace:** ese grupo tiene más carga de deuda y 19.4% de default observado. No se rechaza: se
**verifica el ingreso**, y contando la revisión el indicador sube a 0.93.

*Notas:* la palanca no es cambiar el modelo, es hacer barata la verificación de ingreso.

---

## Slide 6 · La política de decisión

1. **Falta información** (sin buró o sin ingreso) → revisión, nunca rechazo automático.
2. **Riesgo fuera del apetito** (PD ≥ 20%) → rechazo.
3. **Verificación** (ticket > S/ 20,000 o efectivo alto con ticket alto) → revisión.
4. **La cuota no cabe** → contraoferta automática de monto y se recalcula la PD.
5. **Zona gris** (18% a 20%) → revisión. **El resto** → aprobación automática.

**Cómo se reparte:** 53.3% automático · 23.2% revisión · 23.5% rechazo. En los aprobados se ofrece el 90% del monto pedido.

*Notas:* exceder el DTI no manda a analista: dispara contraoferta. Eso libera capacidad para lo que sí requiere criterio.

---

## Slide 7 · Impacto: quién entra y quién sale

| Grupo | Participación | Default observado |
|---|---|---|
| Se mantienen aprobados | 46.9% | 9.8% |
| **Salen** | 35.9% | **19.4%** |
| **Entran** (antes rechazados) | 6.3% | — |

**Cosecha 2025:** la política histórica aprobó 81.6% con 13.4% de default; la propuesta aprueba 64.6% con 9.3%.

*Notas:* el swap-out duplica el default del grupo que se mantiene. El recorte no es al azar: ataca la parte que explicaba
la pérdida.

---

## Slide 8 · El costo, dicho de frente

| Escenario 2025 | Monto colocado | Resultado |
|---|---|---|
| Política histórica | S/ 9.6 M | S/ 1.69 M |
| Propuesta, tasa histórica | S/ 6.2 M | S/ 1.16 M |
| Propuesta con pricing por riesgo | S/ 6.2 M | S/ 0.43 M |

**Dos efectos distintos:** selección −S/ 0.53 M (decisión de riesgo) y precio −S/ 0.73 M (**decisión comercial**).

**Stress:** en el escenario severo la aprobación cae sola de 64.7% a 36.5% y la política absorbe 1.5 puntos de pérdida.
El corte en PD calibrada funciona como **estabilizador automático**.

*Notas:* parte del resultado histórico estaba fuera del apetito de riesgo. No era margen, era riesgo no provisionado.

---

## Slide 9 · Gobierno, monitoreo y puesta en producción

- **Materialidad Tier 1:** validación independiente anual y monitoreo trimestral.
- **Validación independiente:** 10 hallazgos, 2 de severidad alta a remediar antes del despliegue. Conclusión: **apto
  con condiciones**.
- **Monitoreo:** 13 indicadores en datos, modelo y negocio, cada uno con umbral y acción asignada.
- **En producción ya:** API con interfaz web, artefactos versionados con hash y misma respuesta que el desarrollo en 200
  solicitudes verificadas.

*Notas:* si preguntan por reproducibilidad: `python run_all.py` reejecuta todo; 110 pruebas automáticas en verde.

---

## Slide 10 · Qué pedimos al Comité

1. **Aprobar la política y sus umbrales** (PD 18% / 20%, DTI 45% / 60%).
2. **Decidir el margen objetivo del pricing**: el modelo fija el piso, el Comité fija el precio.
3. **Resolver el conflicto de crecimiento**: aceptar 67% de aprobación o ampliar la capacidad de verificación.
4. **Aprobar el marco de gobierno** y las dos remediaciones previas al despliegue.

**Próximo paso inmediato:** remediar los hallazgos de severidad alta y medir la tasa real de aprobación en revisión
durante el primer trimestre.

*Notas:* cerrar con la frase del informe: prestar mejor implica prestar menos; lo que se gana es una cartera que resiste
el escenario adverso sin decisiones de pánico.
