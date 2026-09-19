# 6.8 · Explainability y Fair Lending

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/06_explainability_fairness.ipynb`; código en `src/fairness.py`; tablas `fairness_*.csv`; figuras `fig25` y `fig26`.

---

## 1. Resumen

- **Explicación global.** En el champion, el buró puede mover 70 puntos de score (64% del rango), la capacidad de pago 22 (20%) y el ahorro 18 (16%). En el challenger, SHAP pone al buró muy por delante y reparte aportes chicos entre otras diez variables: usa mucho para ganar poco.
- **Explicación local exacta.** Los puntos que pierde cada característica frente a su mejor tramo **suman** la diferencia de score: una carta de rechazo se puede reconstruir con una tabla en papel. Se documentan tres clientes: aprobado, revisión y rechazado.
- **El score no es un proxy.** Con los insumos del champion no se puede reconstruir región (AUC 0.50), efectivo (R² −0.001), distancia (0.000), edad (−0.001) ni dependientes (−0.002).
- **Impacto de la política.** Por región el AIR va de 0.79 a 1.00 y las regiones que el caso quiere incluir (Oriente y Sur) son las **más** aprobadas. El punto de atención es el quintil de mayor ingreso en efectivo: **AIR 0.74** en aprobación automática, que sube a **0.93** si se cuenta la revisión manual como resultado no adverso.
- La brecha del quintil de mayor efectivo **se repite en OOT 2025** (AIR 0.74), así que no es ruido de un año.
- La diferencia de ese quintil es **de riesgo, no de trato**: su default observado en 2024 fue 19.4% frente a 10%-15% del resto. Aun así, 46.9% de sus clientes buenos no quedan aprobados automáticamente, y ese es el costo de inclusión que la verificación de ingreso debe recuperar.

## 2. Explicación global

| Característica | Rango de puntos | Peso relativo |
|---|---|---|
| Score de buró | 70 (169 a 239) | 64% |
| DTI post-crédito | 22 (185 a 207) | 20% |
| Ahorro sobre monto | 18 (189 a 207) | 16% |

SHAP del challenger (aporte medio absoluto al log-odds): `bureau_score` 0.61, `prior_delinquencies_24m` 0.18, `dti` 0.16, `ahorro_sobre_monto` 0.16, `term_months` 0.12, `dti_post` 0.12, `monthly_debt_payment` 0.12.

Las dos explicaciones coinciden en el fondo —el buró manda, la capacidad de pago sigue— y difieren en la forma. La del champion es una **resta**, no una aproximación: no depende de una librería ni de una muestra de referencia.

## 3. Explicación local: tres clientes

| Caso | Score | PD calibrada | Decisión | Monto solicitado → recomendado | Tasa | Razones |
|---|---|---|---|---|---|---|
| Aprobado automático | 620 | 8.7% | APPROVE | S/ 4,411 → S/ 4,300 | 24.1% | Score de buró bajo · Carga de deuda post-crédito alta |
| Revisión manual | 635 | 6.1% | REVIEW | S/ 6,387 (sin cambio) | 18.0% | Ahorro bajo frente al monto · **Ingreso no informado** |
| Rechazado | 573 | 24.6% | REJECT | — | — | Score de buró bajo · Ahorro bajo frente al monto |

Dos detalles que importan para el trato con el cliente: el caso de revisión **no** es un cliente malo (PD 6.1%), sino uno con el ingreso sin declarar, y la razón lo dice así; y el aprobado recibe una contraoferta de monto, no un rechazo, porque la capacidad de pago no alcanzaba para el monto pedido.

## 4. ¿El score es proxy de un atributo sensible?

La prueba consiste en intentar **reconstruir el atributo sensible a partir de los insumos del champion** (buró, DTI post-crédito y ahorro sobre monto, en WOE), con validación cruzada.

| Atributo | Métrica | Resultado |
|---|---|---|
| Territorio (región) | AUC media / máxima | 0.499 / 0.510 |
| Informalidad (efectivo) | R² | −0.001 |
| Ruralidad (distancia) | R² | 0.000 |
| Edad | R² | −0.001 |
| Composición del hogar | R² | −0.002 |

Ninguno se puede reconstruir: **el scorecard no sabe dónde vive ni cómo cobra el solicitante, y no puede inferirlo**. El score medio por región se mueve 4 puntos (601 a 605) sobre un rango de 110.

## 5. Impacto de la política por grupo

**Aprobación automática (AIR) y "no rechazo" (AIR incluyendo revisión):**

| Grupo | Aprobación automática | AIR | AIR de no rechazo |
|---|---|---|---|
| Oriente | 59.4% | 1.00 | 1.00 |
| Sur | 57.8% | 0.97 | 1.00 |
| Lima | 52.8% | 0.89 | 0.94 |
| Norte | 52.7% | 0.89 | 0.95 |
| Centro | 46.8% | **0.79** | 0.93 |
| Efectivo Q4 | 58.6% | 1.00 | 1.00 |
| Efectivo Q3 | 57.0% | 0.97 | 0.92 |
| Efectivo Q1 (bajo) | 55.4% | 0.95 | 0.96 |
| Efectivo Q2 | 51.8% | 0.88 | 0.93 |
| Efectivo Q5 (alto) | 43.5% | **0.74** | 0.93 |
| Distancia > 50 km (n = 21) | 42.9% | 0.79 | — |
| Edad ≤ 30 | 47.3% | 0.80 | — |
| Canal (los cuatro) | 50.9%-54.0% | 0.94-1.00 | — |

**Confirmación en OOT 2025.** El fairness no puede medirse solo en el año donde se eligió el corte. En 2025, las diferencias territoriales desaparecen (AIR de 0.90 a 1.00, ninguna alerta) y **la brecha del quintil de mayor efectivo se repite casi idéntica: AIR 0.74**. Es decir, no fue un artefacto de 2024: es un patrón estable que hay que gestionar con verificación, no con un ajuste de modelo.

**Tasas de error por grupo** (sobre las solicitudes con resultado observado):

| Grupo | Default observado | Buenos no aprobados | Malos aprobados |
|---|---|---|---|
| Efectivo Q5 (alto) | 19.4% | **46.9%** | 30.2% |
| Efectivo Q4 | 10.3% | 35.4% | 45.8% |
| Efectivo Q1 (bajo) | 14.8% | 42.3% | 42.9% |
| Oriente | 8.8% | 32.3% | 55.6% |
| Centro | 15.5% | 43.8% | 28.6% |

## 6. Riesgos de discriminación indirecta, mitigantes y monitoreo

| Riesgo | Evidencia | Mitigante incorporado | Control de monitoreo |
|---|---|---|---|
| La capacidad de pago funciona como proxy parcial de informalidad | AIR 0.74 en el quintil de mayor efectivo | El efectivo alto con ticket alto va a **verificación**, no a rechazo: el AIR de no rechazo sube a 0.93 | AIR mensual por quintil de efectivo, alerta bajo 0.80 |
| El buró puede estar peor poblado en zonas alejadas | 3.3% de solicitudes sin score | "Sin score" es **revisión con re-consulta**, nunca rechazo automático: la regla precede al rechazo por PD en el motor y una prueba automática lo verifica | Participación y aprobación del segmento sin score |
| Territorio | AIR 0.79 en Centro (0.94 sin rechazo) | Región fuera del modelo por diseño; la brecha viene del perfil de riesgo | AIR territorial del apetito (6.1) |
| Edad | AIR 0.80 en menores de 30 | Edad fuera del modelo; el efecto es indirecto vía relación y ahorro | AIR por tramo de edad |
| Un challenger podría reintroducir proxies | El veto cuesta entre −0.8 y +3.4 puntos de Gini (6.6) | Mismo veto de fairness para todos los modelos | Revisión de fairness obligatoria antes de promover un challenger |

**Acción concreta que se desprende del análisis.** El segmento de mayor informalidad pierde aprobación automática por su carga de deuda y su mayor default, pero casi la mitad de sus clientes buenos queda fuera del canal automático. La palanca no es cambiar el modelo, sino **hacer barata la verificación de ingreso**: visita de campo, evidencia de ventas o movimientos de billetera. Eso convierte revisiones en aprobaciones y es exactamente el objetivo del caso.

## 7. Dos precauciones metodológicas

1. **Asociación, no causalidad.** Que el quintil de mayor efectivo tenga menor aprobación no prueba discriminación por informalidad: ese grupo también trae más carga de deuda y peor comportamiento observado. Las comparaciones de esta sección describen impacto, no mecanismo.
2. **La base no trae sexo ni etnia.** El análisis se limita a los proxies disponibles. En producción la Caja debe medir AIR sobre los atributos protegidos que sí registre, con el mismo formato de esta sección.

## 8. Trazabilidad del requisito 6.8

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Explicación global y local, con SHAP para modelos no lineales | §2 y §3 · `fairness_shap_global.csv` · `fig25` |
| Explicar al menos tres clientes (aprobado, rechazado y revisión) | §3 · `fairness_casos_explicados.csv` |
| Identificar variables sensibles y proxies, y discutir discriminación indirecta | §4 y §6 · `fairness_proxy.csv` |
| Comparar aprobación, score o PD entre al menos dos segmentos, sin conclusiones causales | §5 y §7 · `fairness_air_aprobacion.csv`, `fairness_tasas_error.csv` · `fig26` |
