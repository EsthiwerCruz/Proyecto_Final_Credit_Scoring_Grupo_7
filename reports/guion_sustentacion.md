# Guion de sustentación

**Caso 15 · Caja Rural 360 · Trabajo Integrador Final · Credit Risk & Scoring Analytics 2026**

Formato exigido: **20 minutos de presentación + 15 minutos de preguntas y desafío**, con **demostración en vivo** de
scoring de al menos un solicitante. Cualquier integrante puede ser consultado sobre cualquier componente, así que el
reparto de abajo es para exponer, no para esconderse detrás de una especialidad.

---

## 1. Reparto y tiempos

| Bloque | Slides | Minutos | Expone | Mensaje que no puede faltar |
|---|---|---|---|---|
| Apertura y encargo | 1-2 | 3 | Integrante A | La recomendación de entrada, y el conflicto: no existe corte que cumpla aprobación ≥70% y default ≤11% |
| Datos y modelo | 3-4 | 5 | Integrante B | El deterioro es de nivel, no de mezcla · gana el modelo simple, y por qué |
| Equidad y política | 5-6 | 4 | Integrante C | El score no es proxy · la falta de información se verifica, no se rechaza |
| Impacto y stress | 7-8 | 4 | Integrante D | Swap-out con el doble de default · el costo en soles separando selección de precio |
| Gobierno y cierre | 9-10 | 2 | Integrante A | Validación con 10 hallazgos · las cuatro decisiones que se piden |
| **Demo en vivo** | — | **2** | Integrante B | Un solicitante evaluado de principio a fin con sus razones |

Margen: la presentación suma 20 minutos exactos. Si van retrasados, el bloque que se recorta es el 3 (datos y modelo),
nunca la demo ni el cierre.

## 2. Demo en vivo: guion paso a paso

**Antes de empezar la sustentación** (mientras se conecta el proyector):

```bash
cd Proyecto_Final_Credit_Scoring-main
.venv\Scripts\activate
uvicorn api.main:app --port 8000
```

Abrir `http://localhost:8000/` y dejar la pestaña lista. **Probar una evaluación antes de que entre el jurado**: el
primer arranque tarda unos segundos en cargar los artefactos.

**Durante la demo (2 minutos):**

1. "Este es el servicio que corre en producción. Voy a evaluar una solicitud real de la cosecha 2025."
2. Pulsar **Ejemplo aprobado** → **Evaluar solicitud**. Señalar: decisión, score, PD calibrada, **monto recomendado
   menor al pedido** y tasa.
3. "Fíjense que no le negamos el crédito: le contraofertamos el monto que su cuota resiste. Y estas son las razones,
   que son las mismas que irían en la carta al cliente."
4. Pulsar **Ejemplo en revisión** → **Evaluar**. "Este cliente no es malo: su PD es baja. Lo que falta es el ingreso
   declarado, y la razón lo dice. Va a analista para verificar, no a rechazo."
5. Si el jurado entrega un cliente nuevo: llenar el formulario con sus datos y evaluar en vivo. Si algún campo queda
   vacío en buró, ingreso o ahorros, **el sistema igual responde** y manda a revisión: eso mismo es parte de la
   política.

**Plan B si falla el servicio:** abrir `reports/tables/api_ejemplos.json`, que tiene las tres consultas con su
respuesta completa, y `http://localhost:8000/docs` si el problema fue solo la interfaz.

## 3. Cómo responder las preguntas

El enunciado exige separar cuatro cosas en cada respuesta. Usen esa estructura en voz alta, en este orden:

1. **Hecho observado** — qué dice el dato.
2. **Resultado del modelo** — qué dice la medición.
3. **Supuesto** — qué estamos asumiendo.
4. **Recomendación** — qué haríamos, con número.

---

## 4. Los seis desafíos, respondidos

### Desafío 1 · "El Gini OOT cayó 12 puntos respecto a desarrollo. ¿Puede seguir usándose el modelo?"

- **Hecho observado:** el Gini de nuestro champion se mueve entre cosechas en una banda de 0.35 a 0.49; solo entre 2021
  y 2024 ya hay 14 puntos de diferencia sin que haya pasado nada anormal.
- **Resultado del modelo:** por eso el umbral de monitoreo no es "cayó X puntos", sino un piso absoluto de 0.35 en
  ámbar y 0.30 en rojo, que es el límite inferior de la banda histórica.
- **Supuesto:** que la caída se mide sobre una cosecha cerrada, con volumen suficiente; con menos de 300 casos el
  indicador es ruidoso.
- **Recomendación:** una caída de 12 puntos que deje el Gini dentro de la banda **no justifica retirar el modelo**.
  Se investiga y se revisa primero la **calibración**, que es donde suele estar el problema. Solo si el Gini queda bajo
  0.30 en dos cosechas seguidas se reentrena. Retirar un modelo por una caída que la propia historia produce sería
  cambiar de modelo por ruido.

### Desafío 2 · "El PSI de dos variables críticas supera 0.25, pero el AUC todavía es estable. ¿Qué harían?"

- **Hecho observado:** PSI alto con AUC estable significa que **cambió quién llega**, no que el modelo dejó de ordenar.
- **Resultado del modelo:** en nuestra cartera pasó lo contrario —PSI de 0.005 con deterioro del default— y esa
  distinción fue el hallazgo central: el riesgo cambió de nivel sin cambiar la población.
- **Supuesto:** que el AUC se mide sobre una cosecha con suficiente maduración; si la cosecha es joven, el AUC estable
  puede ser un espejismo.
- **Recomendación:** primero **entender el origen** del cambio de mezcla (campaña, canal nuevo, cambio de proveedor de
  buró). Si es comercial y transitorio, se monitorea y se revisa la calibración, porque un cambio de mezcla mueve el
  nivel de PD aunque el orden aguante. Si es estructural, se reentrena. Lo que no se hace es reentrenar solo porque un
  indicador de estabilidad se pasó de umbral: el PSI es una alerta de investigación, no una orden de reemplazo.

### Desafío 3 · "Negocio pide elevar el approval rate 15 puntos sin modificar la tasa. ¿Qué impactos esperan y qué aprobarían?"

- **Hecho observado:** hoy la política aprueba 67.2% con 10.7% de default y pérdida esperada dentro del apetito.
- **Resultado del modelo:** subir 15 puntos significa llevar el corte de PD de 18% a cerca de 30%. Según la curva de
  trade-off, el default de la cartera sube por encima de 13% y la pérdida esperada supera 3.5%: **se rompen los dos
  límites de riesgo**, no uno. Y el margen no compensa, porque los créditos que entran son los de PD más alta.
- **Supuesto:** que la tasa se mantiene, tal como pide el planteamiento; si se pudiera repreciar, parte del deterioro
  se cubriría con prima de riesgo.
- **Recomendación:** **no se aprueba por corte**. Hay tres caminos que sí se aprueban: ampliar la capacidad de
  verificación, que convierte revisiones en aprobaciones y suma unos 6 puntos sin tocar el riesgo; crecer en los
  segmentos con holgura de cuota, donde el resultado es de 9.4% contra 2.8% en los ajustados; y, si el negocio sigue
  necesitando los 15 puntos, llevar al Comité una **revisión formal del apetito**, con el costo cuantificado. Mover el
  corte sin cambiar el apetito no es una decisión de negocio: es incumplir un límite sin decirlo.

### Desafío 4 · "La PD está bien ordenada, pero subestima el default observado en los deciles 8-10. ¿Qué decisión toman?"

- **Hecho observado:** es exactamente lo que nos pasó: en validación la PD predecía 9.9% donde se observaba 14.0%, y la
  subestimación crecía en las bandas altas.
- **Resultado del modelo:** la recta de calibración tenía pendiente 0.76, no 1. Eso dice que **no es un corrimiento
  paralelo**: corregir solo el intercepto habría dejado mal calibrados justo los deciles que deciden el corte.
- **Supuesto:** que el ordenamiento se mantiene, lo que se verifica con el Gini antes de tocar nada.
- **Recomendación:** **recalibrar, no reentrenar**. Aplicamos Platt con intercepto y pendiente ajustados en validación,
  y lo probamos en la cosecha siguiente: quedó levemente conservador, que es el lado correcto para provisionar.
  Mientras la recalibración no esté vigente, el corte debe endurecerse de forma transitoria, porque cada aprobación se
  está tomando con una PD subestimada cerca de 30%.

### Desafío 5 · "El challenger mejora AUC pero usa variables menos explicables y aumenta latencia. ¿Lo promoverían?"

- **Hecho observado:** nos pasó literalmente: en la cosecha 2025 el challenger dio Gini 0.469 contra 0.424 del champion.
- **Resultado del modelo:** la diferencia de AUC fue +0.022 con intervalo de confianza de −0.002 a +0.044, que
  **incluye el cero**. No es una mejora demostrada, es una diferencia dentro del ruido de una cosecha.
- **Supuesto:** que la comparación se hace sobre la misma población y con el mismo veto de variables sensibles; si el
  challenger gana porque usa edad o región, la comparación no es válida.
- **Recomendación:** **no se promueve**. Queda en seguimiento con una regla escrita: se promueve solo si la ventaja se
  sostiene dos cosechas seguidas con intervalo que excluya el cero, y pasando antes por validación independiente, SHAP
  y el mismo veto de fairness. Un punto de AUC no compensa perder explicación exacta al cliente, multiplicar la
  latencia por cuarenta y sumar dependencias que hay que mantener. Y si alguna vez se promueve, el rollback ya está
  implementado: el champion anterior no se borra, se degrada.

### Desafío 6 · "El escenario Severe incrementa la Expected Loss 70%. ¿Qué segmentos restringirían primero y por qué?"

- **Hecho observado:** en nuestro escenario severo la pérdida esperada pasa de 2.99% a 5.28% del monto, un aumento del
  77%, en línea con el planteamiento.
- **Resultado del modelo:** el tablero de cartera muestra dónde está concentrado el daño. La banda de score 580-600
  tiene el 23% del monto y **el 35% de la pérdida esperada**, con un resultado de 5.4%. El tramo de DTI post-crédito
  sobre 60% rinde 2.8%. En cambio, el tamaño del ticket y la región **no separan rentabilidad**.
- **Supuesto:** que el shock es de nivel y golpea proporcionalmente a toda la cartera; si fuera sectorial, habría que
  segmentar el shock.
- **Recomendación:** restringir en este orden: **primero la banda 580-600**, bajando el corte de aprobación
  automática, porque es donde cada punto de recorte evita más pérdida por sol dejado de colocar; **segundo, el DTI
  sobre 60%**, que solo debería entrar con contraoferta; **tercero, revisar el ticket alto**, no por rentabilidad sino
  por concentración de exposición. Y una advertencia: el modelo ya hace parte del trabajo solo. Como el corte está en
  PD calibrada, un escenario severo reduce la aprobación de 64.7% a 36.5% automáticamente, y esa caída ya absorbe 1.5
  puntos de la pérdida. La restricción manual se suma a eso, no lo reemplaza.

---

## 5. Preguntas probables fuera de la lista

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué excluyeron a los rechazados? | Porque no tienen resultado observable. Tratarlos como buenos habría inflado el desempeño. Entran después por parceling para medir el efecto de la nueva política, y hay un análisis de reject inference como sensibilidad. |
| ¿Por qué no usaron la tasa ofrecida, si predice? | Es endógena: la fijó la política de crédito anterior. Usarla sería aprender la decisión pasada, no el riesgo. |
| ¿Tres variables no son pocas? | Es lo que la evidencia sostiene. Agregar variables mejoraba desarrollo y empeoraba validación. La mora previa, por ejemplo, se invierte fuera de muestra. |
| ¿Por qué el AIR de 0.74 no se corrige en el modelo? | Porque el modelo no usa la informalidad del ingreso: la diferencia viene de carga de deuda y default observado. Corregirlo en el modelo sería igualar por decreto; la vía es verificación, que sube el indicador a 0.93. |
| ¿Cómo sé que el código hace lo que dice el informe? | `python run_all.py` reejecuta todo, 110 pruebas automáticas, y la API responde exactamente lo mismo que el desarrollo en 200 solicitudes verificadas. |
| ¿Qué harían distinto con datos reales? | Revalidar todo el marco: los datos del caso son sintéticos, la LGD no tiene la forma de una cartera real y la exposición no es coherente con el calendario de amortización. Está como hallazgo V-01 y V-10 de la validación. |

## 6. Tres frases para memorizar

1. *"El deterioro fue de nivel, no de mezcla: la misma población incumple más, y eso se arregla recalibrando, no reentrenando."*
2. *"Las solicitudes que salen de la cartera tenían el doble de default que las que se mantienen: el recorte no es al azar."*
3. *"Prestar mejor implica prestar menos. Lo que se gana es una cartera que resiste el escenario adverso sin decisiones de pánico."*

## 7. Checklist del día

- [ ] Servicio levantado y probado **antes** de que entre el jurado
- [ ] Laptop conectada al proyector con la interfaz abierta en una pestaña
- [ ] `api_ejemplos.json` abierto en otra pestaña como plan B
- [ ] Los dos tableros HTML abiertos (cartera y monitoreo)
- [ ] Presentación en modo presentador, con las notas de cada slide visibles
- [ ] Documento técnico y anexo de trazabilidad accesibles por si piden evidencia puntual
- [ ] Los cuatro integrantes con la respuesta a los seis desafíos leída al menos una vez
