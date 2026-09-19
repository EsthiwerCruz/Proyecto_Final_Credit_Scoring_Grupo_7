# 6.15 · Monitoring

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/11_gobierno_monitoreo.ipynb`; código en `src/monitoring.py`; **tablero** en `reports/dashboard_monitoreo.html`; figura `fig35`; tablas `monitoreo_*.csv`.

---

## 1. Resumen

- Tres monitoreos **separados**: **datos** (¿llega la misma población y con la misma calidad?), **modelo** (¿sigue ordenando y con el nivel correcto?) y **negocio** (¿la política produce el resultado esperado?).
- **Trece indicadores** con umbral Verde/Ámbar/Rojo y **una acción concreta con responsable** para cada nivel de alerta.
- Los umbrales salen de lo medido en 6.7, 6.9 y 6.12, no de convenciones: el verde del Gini (0.35) es el piso de la banda histórica entre cosechas, y el de pérdida esperada (3.34%) es el umbral del apetito restateado en base económica.
- **Un umbral hubo que corregirlo con simulación:** el error de calibración medido por trimestre encendía rojo dos veces, pero con cosechas de ~300 créditos una calibración **perfecta** ya produce un ECE mediano de 0.046. Pasó a medirse en **ventana móvil de 12 meses**.
- Simulado sobre la cosecha 2025: datos y modelo en verde; se encienden la **cola de revisión** (23-27% contra capacidad de 20%) y el **default de la cosecha** en dos trimestres. Ambas alertas ya están documentadas como hallazgos V-05 y V-02.

## 2. Qué se monitorea y con qué umbral

| Tipo | Indicador | Verde | Ámbar | Acción ante ámbar | Acción ante rojo | Origen |
|---|---|---|---|---|---|---|
| Datos | PSI del score | ≤ 0.10 | ≤ 0.25 | Investigar el cambio de mezcla y revisar canales | Revisar el modelo: reentrenar si es estructural | 6.7 |
| Datos | PSI de una variable del scorecard | ≤ 0.10 | ≤ 0.25 | Revisar la fuente de esa variable | Reentrenar o reemplazar la variable | 6.7 |
| Datos | Tasa de faltantes de buró | ≤ 5% | ≤ 8% | Revisar la consulta antes de tocar el modelo | Escalar al proveedor; limitar uso | 6.3 |
| Datos | Variación del volumen mensual | ≤ 25% | ≤ 40% | Verificar campañas o cambios de canal | Validar que la mezcla no invalide la calibración | 6.4 |
| Modelo | Gini de la cosecha | ≥ 0.35 | ≥ 0.30 | Investigar: puede ser variación de cosecha | Si persiste dos cosechas, reentrenar | 6.7 |
| Modelo | KS de la cosecha | ≥ 0.25 | ≥ 0.20 | Contrastar con el Gini antes de concluir | Reentrenar | 6.7 |
| Modelo | Observado / predicho | ≤ 1.15 | ≤ 1.30 | Recalibrar con la ventana más reciente | Recalibrar y revisar el punto de corte | 6.7 |
| Modelo | ECE en ventana de 12 meses | ≤ 0.035 | ≤ 0.05 | Recalibrar | Recalibrar y revisar bandas de score | 6.7 |
| Negocio | Aprobación final | ≥ 65% | ≥ 60% | Revisar cola de revisión y capacidad | Escalar al Comité (objetivo, no límite) | 6.9 |
| Negocio | Default 12m de la cosecha | ≤ 11% | ≤ 13% | Revisar calibración antes que el corte | Bajar el umbral automático y escalar | 6.1 y 6.9 |
| Negocio | Pérdida esperada / monto | ≤ 3.34% | ≤ 3.89% | Revisar calibración y mezcla | Recortar la banda 580-600 y escalar | 6.12 |
| Negocio | Cola de revisión manual | ≤ 20% | ≤ 25% | Priorizar por valor esperado | Ampliar capacidad o ajustar umbrales | 6.9 |
| Negocio | AIR por región y por efectivo | ≥ 0.80 | ≥ 0.75 | Revisar la política de verificación | Escalar al Comité: no se compensa | 6.8 |

**El orden de las acciones no es arbitrario:** primero calibración, después punto de corte y solo al final reentrenamiento. La evidencia de 6.4 y 6.7 dice que en esta cartera el problema suele ser de **nivel** y no de ordenamiento, y reentrenar cuando el problema es de calibración cambia el modelo sin resolver nada.

## 3. El umbral que hubo que calibrar con simulación

La primera versión del tablero medía el error de calibración (ECE) **por trimestre** con umbral 0.03, y encendía rojo en dos de los cuatro trimestres de 2025. Antes de reportar eso como deterioro, se simuló cuánto ECE produce una calibración **perfecta** por puro ruido muestral:

| Créditos en la ventana | ECE mediano | ECE p95 |
|---|---|---|
| 300 (un trimestre) | **0.046** | 0.067 |
| 600 (dos trimestres) | 0.032 | 0.048 |
| 1,200 (un año) | 0.023 | 0.033 |
| 3,400 (DEV completo) | 0.014 | 0.020 |

Con cosechas trimestrales, **el umbral de 0.03 era imposible de cumplir aun con calibración perfecta**. El indicador pasó a medirse sobre **ventana móvil de 12 meses** con verde en 0.035 (el p95 del ruido para ese tamaño) y ámbar en 0.05. Con esa definición, el ECE de 2025 va de 0.037 al inicio del año a **0.020 al cierre**, es decir, mejora conforme se acumulan casos, que es exactamente lo que debe pasar.

Es el tipo de detalle que decide si un tablero sirve: un umbral que se enciende por ruido enseña al equipo a ignorar las alertas.

## 4. Simulación sobre la cosecha 2025

| Cosecha | Solicitudes | PSI score | Gini | Obs/pred | ECE 12m | Default | Revisión |
|---|---|---|---|---|---|---|---|
| 2025 Q1 | 286 | 0.039 | 0.390 | 1.04 | 0.037 | 14.3% | 22.7% |
| 2025 Q2 | 305 | 0.006 | 0.367 | 0.83 | 0.029 | 11.8% | 24.3% |
| 2025 Q3 | 308 | 0.033 | 0.475 | 0.82 | 0.035 | 11.7% | 24.0% |
| 2025 Q4 | 290 | 0.038 | 0.454 | 1.08 | **0.020** | 15.9% | 26.9% |

**Semáforo resultante:**

| Tipo | Indicador | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|
| Datos | PSI del score y del buró, faltantes | Verde | Verde | Verde | Verde |
| Modelo | Gini, KS, observado/predicho, ECE 12m | Verde | Verde | Verde | Verde |
| Negocio | Cola de revisión manual | Ámbar | Ámbar | Ámbar | **Rojo** |
| Negocio | Default 12m de la cosecha | **Rojo** | Ámbar | Ámbar | **Rojo** |
| Negocio | Pérdida esperada / monto | Verde | Verde | Verde | Verde |

**Acciones que dispara** (`monitoreo_acciones.csv`):

| Indicador | Estado | Acción | Responsable |
|---|---|---|---|
| Cola de revisión manual | Rojo en Q4 | Ampliar capacidad o ajustar umbrales | Riesgos y Negocio |
| Default 12m de la cosecha | Rojo en Q1 y Q4 | Bajar el umbral de aprobación automática y escalar al Comité | Riesgos y Negocio |

Lo que el tablero dice, leído en conjunto: **el modelo está sano y el entorno es el que empuja**. Datos y discriminación en verde, calibración convergiendo, y las alertas concentradas en negocio, exactamente en los dos puntos que la validación independiente ya había levantado (V-05 sobre capacidad de revisión y V-02 sobre vigencia de la calibración). Un tablero que enciende lo mismo que encontró la validación es señal de que ambos están midiendo bien.

## 5. Calendario de monitoreo

| Frecuencia | Alcance | Qué se revisa | Responsable |
|---|---|---|---|
| Diario | Datos y operación | Volumen, faltantes, errores del servicio, latencia | Analytics / TI |
| Mensual | Datos y negocio | PSI del score y de variables, mezcla de decisiones, cola de revisión, AIR | Analytics |
| Trimestral | Modelo y negocio | Gini, KS, calibración y EL de la cosecha cerrada; semáforo del apetito | Riesgos |
| Anual | Gobierno | Validación independiente completa, revisión de Model Card y de apetito | Validación y Comité |

**Un matiz que importa:** el monitoreo de modelo necesita **cosechas cerradas**. El default a 12 meses de una solicitud de enero recién se conoce en enero del año siguiente, así que Gini y calibración siempre miran hacia atrás. Por eso el monitoreo de **datos** es diario y mensual: es la única alerta temprana disponible, y un PSI que se dispara hoy avisa de un problema que el Gini recién confirmaría dentro de un año.

## 6. Tablero

`reports/dashboard_monitoreo.html` es autocontenido (tablas y figuras embebidas, sin dependencias externas) y se regenera con cada corrida del notebook 11. Incluye indicadores por cosecha, semáforo por tipo, acciones ante alerta, umbrales con su origen y el calendario.

## 7. Limitaciones

1. **El monitoreo de modelo está simulado sobre una cosecha cerrada.** En producción real, el primer semáforo de modelo llega recién a los 12 meses del despliegue.
2. **No hay monitoreo de la calidad del servicio bajo carga** (errores, timeouts, latencia p99 real): queda definido en el calendario diario pero no medido aquí.
3. **El AIR requiere volumen para ser estable**: con cortes mensuales y segmentos chicos, conviene leerlo con ventana móvil, igual que el ECE.
4. **Los umbrales de negocio dependen del apetito vigente**: si el Comité restatea el apetito, hay que restatear el tablero en la misma base (como se hizo con la pérdida esperada en 6.12).

## 8. Trazabilidad del requisito 6.15

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Tablero con indicadores de data drift, performance, calibración, cartera y operación | §4 y §6 · `reports/dashboard_monitoreo.html` · `fig35` |
| Umbrales Verde/Ámbar/Rojo para PSI, Gini/KS, calibración, approval rate, default rate y EL | §2 · `monitoreo_umbrales.csv` |
| Qué acción se ejecuta ante cada alerta | §2 y §4 · `monitoreo_acciones.csv` |
| Distinguir monitoreo de datos, de modelo y de negocio | §2 · columna `tipo` en todas las tablas y en el tablero |
