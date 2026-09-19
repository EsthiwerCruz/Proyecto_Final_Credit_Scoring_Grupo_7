# 6.6 · Modelos PD y estrategia Champion/Challenger

**Caso 15 · Caja Rural 360**

> **Evidencia:** `notebooks/04_modelos_pd.ipynb`; código en `src/models.py`; tablas `modelos_*.csv`; figura `fig22`; artefacto `models/challenger_lgbm_v1.joblib`.

---

## 1. Resumen

- Se entrenaron **seis candidatos** sobre la misma población, la misma partición temporal y el mismo preprocesamiento: el scorecard de 6.5, una logística sobre el pipeline completo, Random Forest, XGBoost, LightGBM y LightGBM con restricciones de monotonía.
- El tuning usó **validación temporal dentro de DEV** (2021 → 2022 y 2021-2022 → 2023). VAL solo comparó modelos ya entrenados; el OOT no se tocó.
- **Todos los challengers llevan el mismo veto de fairness que el champion**: edad, región, distancia, dependientes e ingreso en efectivo quedan fuera de la matriz (23 columnas en lugar de 32).
- **Champion: el scorecard de 6.5. Challenger: LightGBM monótono.** El scorecard es a la vez el más simple y el de mejor Gini fuera de muestra, así que la regla de selección no necesitó arbitrar.
- Ningún modelo está calibrado: todos subestiman el nivel de 2024 en la misma proporción (observado/predicho entre 1.41 y 1.45). El problema de nivel es del entorno, no del algoritmo, y se corrige en 6.7.

## 2. Candidatos y grillas

Las grillas son chicas y con racional: con 351 defaults en DEV, una búsqueda masiva encuentra ruido (6.4 mostró que la señal vive en pocas variables).

| Modelo | Grilla | Mejor configuración | Gini medio fuera del fold |
|---|---|---|---|
| Regresión logística (23 columnas) | C ∈ {0.05, 0.25, 1.0} | C = 0.05 | 0.388 |
| Random Forest | profundidad {4,6} × hoja mínima {20,50} × variables {sqrt, 0.5} | prof. 6, hoja 50, 0.5 | 0.380 |
| XGBoost | profundidad {2,3} × árboles {200,400} × peso mínimo {20,50} | prof. 2, 200, peso 50 | 0.375 |
| LightGBM | hojas {7,15} × árboles {200,400} × casos mínimos {30,60} | 7 hojas, 200, 30 casos | 0.335 |
| LightGBM monótono | misma configuración, con dirección de negocio impuesta | — | 0.368 |
| Scorecard WOE (6.5) | sin tuning: tramos y coeficientes de 6.5 | — | 0.354 |

En los cuatro casos ganó la configuración **más conservadora** de la grilla: profundidad 2, hojas chicas, mínimo alto de casos por hoja y la regularización más fuerte de la logística.

## 3. Comparación integral

| Modelo | Variables | Gini DEV | Gini CV temporal | Gini VAL | Brecha DEV−VAL | O/E en VAL | ms / 1,000 solicitudes |
|---|---|---|---|---|---|---|---|
| **Scorecard WOE (6.5)** | 3 | 0.440 | 0.354 | **0.348** | **0.092** | 1.41 | **0.47** |
| Regresión logística | 23 | 0.440 | 0.388 | 0.338 | 0.103 | 1.44 | 15.4 |
| Random Forest | 23 | 0.553 | 0.380 | 0.320 | 0.233 | 1.41 | 37.4 |
| LightGBM monótono | 23 | 0.620 | 0.368 | 0.309 | 0.311 | 1.44 | 24.5 |
| XGBoost | 23 | 0.526 | 0.375 | 0.309 | 0.217 | 1.44 | 19.7 |
| LightGBM | 23 | 0.755 | 0.335 | 0.304 | 0.451 | 1.45 | 24.2 |

Tres lecturas:

1. **El sobreajuste es enorme en los modelos libres.** LightGBM llega a 0.755 en DEV y cae a 0.304 en VAL. El scorecard tiene la menor brecha (9 puntos) porque tiene tres características en tramos.
2. **Fuera de muestra nadie le gana al scorecard.** Y las restricciones de monotonía ayudan: el LightGBM monótono mejora medio punto de Gini en VAL sobre el libre y recorta 14 puntos de brecha.
*Nota de reproducibilidad: la latencia es la única cifra del repositorio que cambia entre corridas, porque depende de la máquina (entre corridas varió de 0.4 a 0.5 ms el scorecard y de 20 a 37 ms los árboles). El orden de magnitud es lo que importa.*

3. **El costo operativo es de otro orden.** El scorecard puntúa 1,000 solicitudes en medio milisegundo; los árboles necesitan entre 20 y 40, más artefacto binario y dependencias (`lightgbm`, `xgboost`) que hay que versionar y mantener en producción.

## 4. Regla de selección y decisión

Regla fijada antes de ver los resultados: **gana el modelo más simple cuya discriminación fuera de muestra no sea significativamente peor que la del mejor** (bootstrap pareado sobre VAL, IC 95% de la diferencia de AUC). El mayor AUC no decide solo, como exige el enunciado.

| Modelo | Orden de simplicidad | Gini VAL | Δ AUC vs. mejor | IC 95% | ¿Peor de forma significativa? |
|---|---|---|---|---|---|
| Scorecard WOE | 1 | 0.348 | — | — | — |
| Regresión logística | 2 | 0.338 | −0.005 | −0.028 a +0.017 | No |
| LightGBM monótono | 3 | 0.309 | −0.020 | −0.044 a +0.003 | No |
| LightGBM | 4 | 0.304 | −0.022 | −0.050 a +0.002 | No |
| XGBoost | 5 | 0.309 | −0.020 | −0.041 a −0.000 | **Sí** |
| Random Forest | 6 | 0.320 | −0.014 | −0.032 a +0.002 | No |

**Champion: scorecard de 6.5.** Es el más simple y además el de mejor Gini en VAL. Los demás criterios apuntan igual: menor brecha DEV-VAL, calibración corregible con dos parámetros, explicación local exacta por puntos, artefacto JSON auditable y latencia de sub-milisegundo.

**Challenger: LightGBM monótono.** Se prefiere sobre el LightGBM libre porque impone la dirección de negocio documentada en 6.5, reduce el sobreajuste y es defendible ante un validador. Queda en seguimiento para volver a competir cuando haya más cosechas; 6.7 lo vuelve a comparar contra el champion sobre el OOT.

## 5. El costo de la restricción de fairness

| Modelo | Gini VAL con veto | Gini VAL sin veto | Diferencia |
|---|---|---|---|
| Regresión logística | 0.338 | 0.330 | **−0.008** |
| LightGBM monótono | 0.309 | 0.343 | +0.034 |
| XGBoost | 0.309 | 0.326 | +0.018 |

Levantar el veto (dejar entrar edad, región, distancia, dependientes y efectivo) mueve el Gini entre −0.8 y +3.4 puntos según el algoritmo, y ni siquiera en la misma dirección: la logística **empeora**. El costo predictivo de la restricción es pequeño e inestable; el costo reputacional y regulatorio de decidir con esas variables es cierto. Además, ningún modelo con veto levantado supera al champion en VAL.

## 6. Limitaciones

- Los modelos de árboles se entrenaron con la matriz imputada del pipeline de 6.3; podrían manejar faltantes de forma nativa, pero se privilegió que **todos los candidatos vean exactamente el mismo dato**.
- El tuning es deliberadamente acotado. Con dos folds y 351 defaults, una búsqueda más fina habría elegido ruido: la propia grilla ya muestra que la mejor configuración es la más regularizada.
- La comparación de calibración en esta sección es descriptiva; la corrección formal y las métricas sobre OOT son de 6.7.

## 7. Trazabilidad del requisito 6.6

| Requisito del enunciado | Dónde se cumple |
|---|---|
| Entrenar logística, Random Forest, XGBoost y LightGBM | §2 y §3 · `src/models.py` · notebook §2 |
| Tuning razonable y controlado, con racional | §2 · `models.GRIDS` y validación temporal dentro de DEV |
| Comparar discriminación, calibración, estabilidad, interpretabilidad y complejidad operativa | §3 · `modelos_comparacion.csv` · `fig22` |
| Champion y al menos un Challenger, sin decidir solo por AUC | §4 · regla pre-registrada · `modelos_champion_challenger.csv` |
