"""Gobierno y Model Risk Management (sección 6.14).

Tres piezas que tienen que existir para que un modelo pueda operar en una entidad:

* **Model Card**: qué hace, con qué datos, qué tan bien, qué no debe hacer y quién responde.
  Se genera desde los artefactos y las tablas, así que no puede quedar desactualizada.
* **Inventario, materialidad y ciclo de vida**: qué modelos hay, cuánto pesan, quién
  aprueba cada paso y con qué frecuencia se revisan.
* **Validación independiente**: hallazgos con severidad, evidencia, impacto, recomendación
  y responsable. Un informe de validación sin hallazgos no es una buena noticia: es una
  validación que no miró.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from . import config as cfg
from . import registry as reg

# ---------------------------------------------------------------------------
# Materialidad y ciclo de vida
# ---------------------------------------------------------------------------
CRITERIOS_MATERIALIDAD = [
    ("Exposición gestionada", "Decide sobre el 100% de las solicitudes del producto", 3),
    ("Automatización de la decisión", "Aprueba y rechaza sin intervención humana en ~77% de los casos", 3),
    ("Impacto en resultados", "Determina pérdida esperada y pricing de toda la originación", 3),
    ("Exposición regulatoria y reputacional", "Decisión de crédito a personas; sujeto a fair lending", 3),
    ("Complejidad del modelo", "Scorecard lineal de 3 características, interpretable", 1),
    ("Dependencia de terceros", "Una fuente externa crítica: el score de buró", 2),
]

NIVELES = {range(0, 9): ("Tier 3 · baja", "Revisión anual documental"),
           range(9, 14): ("Tier 2 · media", "Validación independiente cada 2 años y monitoreo trimestral"),
           range(14, 19): ("Tier 1 · alta", "Validación independiente anual, monitoreo trimestral y reporte al Comité")}

CICLO_DE_VIDA = [
    ("1. Propuesta", "Caso de negocio, población y target", "Analytics", "Jefatura de Riesgos"),
    ("2. Desarrollo", "Datos, features, modelo y política (6.1 a 6.9)", "Analytics", "—"),
    ("3. Validación independiente", "Revisión metodológica y hallazgos (6.14)", "Validación", "Validación firma"),
    ("4. Aprobación", "Decisión de uso, apetito y umbrales", "Comité de Riesgos", "Comité de Riesgos"),
    ("5. Despliegue", "Promoción en el Model Registry y publicación de la API", "Analytics + TI", "Jefatura de Riesgos"),
    ("6. Monitoreo", "Datos, modelo y negocio con semáforos (6.15)", "Analytics y Riesgos", "—"),
    ("7. Recalibración / reentrenamiento", "Disparado por umbrales, no por calendario", "Analytics", "Validación"),
    ("8. Retiro o rollback", "Degradación del champion y promoción del anterior", "Comité de Riesgos", "Comité de Riesgos"),
]

LINEAS_DE_DEFENSA = [
    ("Primera línea", "Analytics y Negocio",
     "Construye el modelo y la política, ejecuta el monitoreo operativo y documenta",
     "Model Card, tablero de monitoreo, registro de decisiones"),
    ("Segunda línea", "Riesgos y Validación independiente",
     "Desafía la metodología, valida antes del uso, aprueba cambios de champion y vigila el apetito",
     "Informe de validación, semáforo del apetito, actas del Comité"),
    ("Tercera línea", "Auditoría interna",
     "Comprueba que el marco se cumpla y que todo sea reproducible y trazable",
     "Checklist de auditoría, hash de artefactos, reejecución del repositorio"),
]

CHECKLIST_AUDITORIA = [
    ("Reproducibilidad", "`python run_all.py` reejecuta todo y regenera tablas, figuras y artefactos idénticos"),
    ("Integridad de artefactos", "El hash SHA-256 de cada artefacto coincide con el Model Registry (`/health`)"),
    ("Trazabilidad de decisiones", "Cada respuesta de la API trae `trace_id` y versión de modelo, calibrador y política"),
    ("Separación de muestras", "El OOT se usó una sola vez; ninguna decisión se ajustó con él (6.2 y 6.7)"),
    ("Leakage", "Lista de variables prohibidas documentada y verificada por prueba automática (6.2 y 6.3)"),
    ("Fairness", "AIR por región, efectivo, edad y distancia, con prueba de proxy sobre los insumos (6.8)"),
    ("Calibración vigente", "Fecha del último ajuste del calibrador y resultado del último semáforo (6.7 y 6.15)"),
    ("Aprobaciones", "Acta del Comité que aprueba el champion, el apetito y los umbrales de decisión"),
    ("Pruebas automáticas", "La suite corre en verde y cubre contrato de la API, política y modelos"),
    ("Plan de remediación", "Cada hallazgo de validación tiene responsable y fecha comprometida"),
]

# ---------------------------------------------------------------------------
# Validación independiente simulada
# ---------------------------------------------------------------------------
# id, severidad, título, evidencia, impacto, recomendación, responsable, plazo
HALLAZGOS = [
    ("V-01", "Alta", "La exposición al default no es coherente con el calendario de amortización",
     "El 49.3% de los defaults implica más de 12 cuotas pagadas, imposible con la ventana de 12 meses (6.10 §3)",
     "El factor de exposición de 0.415 puede estar sesgado; afecta pérdida esperada, pricing y provisiones",
     "Elevar al dueño del dato antes de usar el modelo para provisiones; reestimar EAD con datos corregidos",
     "Dueño del dato + Analytics", "Antes del despliegue"),
    ("V-02", "Alta", "La calibración envejece rápido y el modelo subestima el riesgo sin corrección",
     "Observado/predicho de 1.41 en VAL y 1.31 en OOT antes de recalibrar (6.7 §4)",
     "Sin recalibración vigente, la PD subestima ~30% y la pérdida esperada de la cartera queda subestimada igual",
     "Fijar la recalibración como control obligatorio con disparador automático y dueño asignado; bloquear el uso si vence",
     "Analytics", "Trimestral, permanente"),
    ("V-03", "Media", "Los parámetros de EAD y LGD son constantes sobre 351 defaults de desarrollo",
     "Ningún modelo supera al baseline global fuera de muestra y no hay muestra para segmentar (6.10 y 6.11)",
     "Riesgo de sesgo por segmento no detectado en pérdida esperada y capital",
     "Revisión anual con la nueva cosecha; segmentar en cuanto haya casos suficientes por banda de riesgo",
     "Analytics", "Revisión anual"),
    ("V-04", "Media", "Impacto adverso en el segmento de mayor ingreso en efectivo",
     "AIR de 0.74 en aprobación automática en 2024 y 0.74 en 2025, por debajo de la regla de los 4/5 (6.8 §5)",
     "Riesgo de fair lending y de contradecir el objetivo de inclusión del caso",
     "Medir mensualmente el AIR y evidenciar que la verificación de ingreso convierte revisiones en aprobaciones; reportar al Comité",
     "Riesgos", "Mensual"),
    ("V-05", "Media", "La cola de revisión manual excede la capacidad declarada",
     "La política genera 23.2% de revisiones contra una capacidad de 20% (6.9 §7)",
     "Riesgo operativo: decisiones tomadas sin la verificación que la política supone, o demoras en la respuesta",
     "Priorizar por valor esperado, medir el cumplimiento del SLA de revisión y evaluar ampliar capacidad",
     "Operaciones + Riesgos", "Antes del despliegue"),
    ("V-06", "Media", "El supuesto de que el analista aprueba el 60% de las revisiones no está validado",
     "La aprobación final esperada (67.2%) depende de ese supuesto; con 40% baja a 62.6% (6.9 §10)",
     "La proyección de volumen y de ingresos puede desviarse de forma material",
     "Medir la tasa real de aprobación en revisión durante los primeros tres meses y recalcular la proyección",
     "Operaciones", "Primer trimestre de uso"),
    ("V-07", "Media", "Concentración en un único proveedor de información externa",
     "El score de buró explica el 64% del rango de puntos del scorecard (6.8 §2)",
     "Una caída o cambio de escala del buró degrada la decisión de toda la cartera",
     "Documentar plan de contingencia: regla de negocio temporal si el buró no responde y prueba de estrés del proveedor",
     "TI + Riesgos", "Antes del despliegue"),
    ("V-08", "Baja", "El challenger superó al champion en la cosecha OOT sin significancia estadística",
     "Gini 0.469 contra 0.424, con intervalo de −0.002 a +0.044 que incluye el cero (6.7 §7)",
     "Posible pérdida de poder predictivo frente a una alternativa disponible",
     "Mantener el challenger en seguimiento y promover solo si la ventaja se sostiene dos cosechas con intervalo que excluya el cero",
     "Analytics", "Revisión semestral"),
    ("V-09", "Baja", "No se aplicó reject inference al modelo campeón",
     "El scorecard se ajusta solo con aprobados; la sensibilidad muestra ranking estable (Spearman 0.9996) (6.5 §8)",
     "Riesgo bajo dado el filtro histórico débil, pero la nueva política aprobará perfiles antes rechazados",
     "Monitorear el default de los aprobados en bandas bajas y reevaluar con la primera cosecha de la nueva política",
     "Analytics", "A los 12 meses de uso"),
    ("V-10", "Informativo", "Los datos son sintéticos y la severidad no se comporta como una cartera real",
     "LGD unimodal sin masa en 0 ni en 1, y ninguna variable de T0 explica EAD ni LGD (6.11 §2)",
     "Los parámetros no son trasladables a la cartera real sin revalidar",
     "Revalidar todo el marco con datos reales antes de cualquier uso productivo",
     "Analytics + Validación", "Antes de producción real"),
]

COLUMNAS_HALLAZGOS = ["id", "severidad", "hallazgo", "evidencia", "impacto", "recomendacion", "responsable", "plazo"]


def materialidad() -> tuple[pd.DataFrame, dict]:
    """Clasificación de materialidad del modelo y su frecuencia de revisión."""
    t = pd.DataFrame(CRITERIOS_MATERIALIDAD, columns=["criterio", "situación en este modelo", "puntaje"])
    total = int(t["puntaje"].sum())
    nivel, frecuencia = next((v for r, v in NIVELES.items() if total in r), ("Tier 1 · alta", "Validación anual"))
    return t, {"puntaje": total, "maximo": len(CRITERIOS_MATERIALIDAD) * 3, "nivel": nivel, "frecuencia": frecuencia}


def ciclo_de_vida() -> pd.DataFrame:
    return pd.DataFrame(CICLO_DE_VIDA, columns=["etapa", "contenido", "ejecuta", "aprueba"])


def lineas_de_defensa() -> pd.DataFrame:
    return pd.DataFrame(LINEAS_DE_DEFENSA, columns=["línea", "quién", "responsabilidad", "evidencia que produce"])


def hallazgos() -> pd.DataFrame:
    return pd.DataFrame(HALLAZGOS, columns=COLUMNAS_HALLAZGOS).set_index("id")


def checklist_auditoria() -> pd.DataFrame:
    return pd.DataFrame(CHECKLIST_AUDITORIA, columns=["control", "evidencia verificable"])


# ---------------------------------------------------------------------------
# Model Cards
# ---------------------------------------------------------------------------
def build_model_card(ruta, desempeno: pd.DataFrame, puntos: pd.DataFrame, calibrador: dict,
                     politica: dict, air_minimo: float) -> str:
    """Genera la Model Card del champion desde los artefactos y las tablas de resultados."""
    inv = reg.inventory()
    card = inv.loc["scorecard_pd"]
    m = materialidad()[1]
    fila = lambda muestra, col: f"{desempeno.loc[(desempeno['modelo'].str.startswith('Champion')) & (desempeno['muestra'] == muestra), col].iloc[0]:.3f}"
    texto = f"""# Model Card · Scorecard PD — Caja Rural 360

*Generada automáticamente por `governance.build_model_card` el {date.today().isoformat()}. No editar a mano: se regenera con el notebook 11.*

## 1. Identificación

| Campo | Valor |
|---|---|
| Nombre | Scorecard PD · microcrédito rural |
| Versión | {card['version']} · artefacto `{card['archivo']}` |
| Hash SHA-256 | `{card['sha256'][:32]}…` |
| Estado | {card['estado']} |
| Dueño | {card['dueño']} |
| Entrenado con | {card['entrenado_con']} |
| Materialidad | {m['nivel']} ({m['puntaje']} de {m['maximo']} puntos) · {m['frecuencia']} |

## 2. Propósito y uso

**Para qué es.** Estimar la probabilidad de que un microcrédito rural alcance 90 días de mora dentro de los 12 meses siguientes al desembolso, y alimentar la decisión automática de originación (APPROVE / REVIEW / REJECT), el monto recomendado y el pricing por riesgo.

**Para qué NO es.** No estima recuperación ni severidad (eso es EAD y LGD), no decide cobranza ni gestión de cartera vigente, no sirve para carteras distintas del microcrédito rural, y **no debe usarse sin el calibrador vigente**: la PD del scorecard es de desarrollo.

**Quién lo consume.** El servicio de scoring (`api/main.py`) en la originación web, app, agencia y alianza, y el motor de decisión de 6.9.

## 3. Datos

| Aspecto | Detalle |
|---|---|
| Población | Solicitudes aprobadas con performance observable (`outcome_available_flag = 1`) |
| Target | `default_12m_flag`: 90+ días de mora dentro de 12 meses de `observation_date` |
| Muestras | DEV 2021-2023 (3,443 créditos, 351 defaults) · VAL 2024 · OOT 2025 |
| Variables | `bureau_score`, `dti_post` (DTI post-crédito), `ahorro_sobre_monto` |
| Excluidas por diseño | Edad, región, distancia, dependientes e ingreso en efectivo (fairness, 6.5) |
| Excluidas por leakage | Campos post-decisión y post-default; tasa ofrecida por endógena (6.2) |
| Tratamiento de faltantes | Imputación con la mediana de DEV; en el scorecard, WOE neutral |

## 4. Metodología

Binning supervisado con mínimos de 5% de la muestra y 15 defaults por tramo, monotonía en la dirección de negocio, WOE e IV, selección con siete criterios pre-registrados (S1 a S7) y regresión logística sobre los WOE. Escala: **{politica.get('base_score', 600)} puntos = odds {politica.get('base_odds', 10)}:1, PDO {politica.get('pdo', 20)}**. La PD de producción es `Platt(PD del scorecard)` con intercepto {calibrador['intercepto']:.3f} y pendiente {calibrador['pendiente']:.3f}, ajustado en VAL.

**Tabla de puntos** (resumen; completa en `reports/tables/scorecard_puntos.csv`):

{puntos.groupby('variable')['puntos'].agg(['min', 'max']).to_markdown()}

## 5. Desempeño

| Muestra | Gini | KS | Brier | Observado/predicho (antes de calibrar) |
|---|---|---|---|---|
| DEV | {fila('DEV', 'gini')} | {fila('DEV', 'ks')} | {fila('DEV', 'brier')} | {fila('DEV', 'observado_sobre_predicho')} |
| VAL | {fila('VAL', 'gini')} | {fila('VAL', 'ks')} | {fila('VAL', 'brier')} | {fila('VAL', 'observado_sobre_predicho')} |
| OOT | {fila('OOT', 'gini')} | {fila('OOT', 'ks')} | {fila('OOT', 'brier')} | {fila('OOT', 'observado_sobre_predicho')} |

Rango del Gini entre cosechas: 0.35 a 0.49. Una caída dentro de esa banda **no** es deterioro.

## 6. Fairness

Ninguna variable sensible entra al modelo y los insumos no permiten reconstruirlas (AUC 0.50 para región; R² ≈ 0 para efectivo, distancia, edad y dependientes). El AIR más bajo de la política es {air_minimo:.2f}, en el quintil de mayor ingreso en efectivo, que se atiende con verificación y no con rechazo (hallazgo V-04).

## 7. Limitaciones

- La PD es de desarrollo: **requiere calibrador vigente**.
- Tres características son pocas, pero es lo que la evidencia sostiene: agregar variables sin señal mejora DEV y empeora VAL.
- Un solo scorecard para todos los canales y regiones (justificado en 6.4).
- Datos sintéticos: los parámetros no son trasladables a cartera real sin revalidar.

## 8. Monitoreo y disparadores

Semáforos y acciones en 6.15. Disparan recalibración: observado/predicho fuera de [0.85, 1.15] dos meses seguidos, o pérdida esperada de la cosecha sobre 3.34%. Dispara revisión de reentrenamiento: Gini bajo 0.30 o PSI del score sobre 0.10.

## 9. Gobierno

| Evento | Quién aprueba |
|---|---|
| Uso del modelo y umbrales de decisión | Comité de Riesgos |
| Promoción de challenger a champion | Comité de Riesgos, con validación independiente previa |
| Recalibración dentro de umbrales | Jefatura de Riesgos (informa al Comité) |
| Rollback | Jefatura de Riesgos, registrado en el Model Registry |

## 10. Reproducibilidad

Semilla {cfg.SEED}, versiones fijadas en `requirements.txt`, artefacto versionado con hash en `models/registry.json`. `python run_all.py` reejecuta todo el proyecto y regenera este documento.
"""
    ruta = str(ruta)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta


def build_short_card(ruta, titulo: str, seccion: str, artefacto: dict, contenido: dict) -> str:
    """Ficha resumida para EAD y LGD."""
    filas = "\n".join(f"| {k} | {v} |" for k, v in contenido.items())
    texto = f"""# Ficha técnica · {titulo}

*Sección {seccion} · generada el {date.today().isoformat()} desde `models/{artefacto['archivo']}`.*

| Campo | Valor |
|---|---|
{filas}
"""
    with open(str(ruta), "w", encoding="utf-8") as f:
        f.write(texto)
    return str(ruta)


def validation_report(ruta, resumen: dict) -> str:
    """Informe de validación independiente simulada, con hallazgos y plan de remediación."""
    h = hallazgos().reset_index()
    conteo = h["severidad"].value_counts().to_dict()
    texto = f"""# Informe de validación independiente (simulada)

**Modelo:** Scorecard PD · Caja Rural 360 · versión 1.0
**Alcance:** secciones 6.1 a 6.13 del Trabajo Integrador Final
**Fecha:** {date.today().isoformat()}
**Conclusión:** {resumen['conclusion']}

## 1. Alcance y método

Revisión de la definición de target y población, la partición temporal, el tratamiento de datos, la
construcción y selección del scorecard, la calibración, el análisis de fairness, el motor de decisión, los
parámetros de EAD y LGD, la integración en pérdida esperada y el servicio de scoring. Se reejecutó el
repositorio completo, se verificó la integridad de los artefactos contra el Model Registry y se contrastaron
las cifras de los reportes contra las tablas generadas.

## 2. Resultado general

{resumen['resultado_general']}

**Hallazgos:** {conteo.get('Alta', 0)} de severidad alta, {conteo.get('Media', 0)} media, {conteo.get('Baja', 0)} baja y {conteo.get('Informativo', 0)} informativo.

## 3. Hallazgos y plan de remediación

{h.to_markdown(index=False)}

## 4. Lo que se verificó y está conforme

{chr(10).join('- ' + x for x in resumen['conforme'])}

## 5. Opinión

{resumen['opinion']}
"""
    with open(str(ruta), "w", encoding="utf-8") as f:
        f.write(texto)
    return str(ruta)
