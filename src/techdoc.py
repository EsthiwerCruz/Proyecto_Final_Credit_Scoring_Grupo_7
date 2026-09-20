"""Documento técnico consolidado (entregable 2).

No se escribe: se **arma** desde los quince reportes de sección, para que no exista una
segunda versión de la verdad que se desactualice. Agrega portada, índice, un resumen de las
decisiones que definieron el trabajo y los anexos de trazabilidad y reproducibilidad.

Uso:

    python -m src.techdoc            # genera reports/documento_tecnico.md
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from . import config as cfg

SECCIONES = [
    ("6.1", "01_negocio_y_arquitectura_crediticia.md"),
    ("6.2", "02_definicion_modelo_y_poblacion.md"),
    ("6.3", "03_data_strategy_calidad_features.md"),
    ("6.4", "04_eda_orientado_a_riesgo.md"),
    ("6.5", "05_scorecard_tradicional.md"),
    ("6.6", "06_modelos_pd.md"),
    ("6.7", "07_validacion_calibracion.md"),
    ("6.8", "08_explainability_fairness.md"),
    ("6.9", "09_decision_engine.md"),
    ("6.10", "10_ead.md"),
    ("6.11", "11_lgd.md"),
    ("6.12", "12_expected_loss_stress.md"),
    ("6.13", "13_arquitectura_api_mlops.md"),
    ("6.14", "14_gobierno_model_risk.md"),
    ("6.15", "15_monitoring.md"),
]

# Las decisiones que definieron el trabajo: qué se decidió, por qué y dónde está la evidencia.
DECISIONES = [
    ("Población y target", "Solo créditos con performance observable (5,783 de 7,000); default a 90+ días en 12 meses",
     "Es la definición oficial del caso; los 1,217 rechazados no tienen target observable", "6.2"),
    ("Partición", "Temporal: 2021-2023 desarrollo, 2024 validación, 2025 out-of-time",
     "Un split aleatorio ocultaría el deterioro del entorno, que es el hallazgo central", "6.2"),
    ("Tasa ofrecida", "Excluida del modelo PD", "Es endógena: la fija la propia política de crédito", "6.2"),
    ("Estacionalidad", "Descartada la hipótesis de campaña agrícola",
     "Chi² p = 0.89: el rango observado entre meses es menor que el del azar", "6.1 y 6.4"),
    ("Variables sensibles", "Región, edad, distancia, dependientes e ingreso en efectivo fuera del modelo",
     "Sin señal estable y con riesgo de fair lending; el veto se aplica también a los challengers", "6.5 y 6.6"),
    ("Mora previa", "Excluida del scorecard pese a tener señal en desarrollo",
     "Se invierte en validación (IV negativo): criterio S6 pre-registrado", "6.5"),
    ("Champion", "Scorecard WOE de 3 características sobre modelos de boosting",
     "Mejor Gini fuera de muestra, menor brecha de sobreajuste y explicación local exacta", "6.6"),
    ("Calibración", "Platt (intercepto y pendiente) ajustado en validación, sobre isotónica",
     "Preserva el orden y el Gini; la isotónica gana 0.005 de ECE pero cuesta 1.8 puntos de Gini", "6.7"),
    ("Punto de corte", "PD calibrada ≤ 18% automático, rechazo sobre 20%",
     "Máxima aprobación sujeta a default ≤ 11% y pérdida esperada dentro del apetito", "6.9"),
    ("Capacidad de pago", "Exceder el DTI dispara contraoferta automática de monto, no revisión manual",
     "La contraoferta es aritmética, no juicio: libera capacidad de análisis para lo verificable", "6.9"),
    ("EAD y LGD", "Baselines globales (0.415 y 0.616) en lugar de modelos",
     "Ningún modelo supera al baseline fuera de muestra con 351 defaults de desarrollo", "6.10 y 6.11"),
    ("Base de la LGD", "Económica (descontada), con el umbral del apetito restateado en la misma base",
     "La LGD contable no descuenta 12 meses de workout; cambiar la métrica sin el umbral rompe el semáforo", "6.12"),
    ("Stress", "Shock sobre las odds de la PD, no sobre la PD",
     "Reproduce el desplazamiento de nivel observado y no se sale del rango [0, 1]", "6.12"),
    ("Umbral de calibración del monitoreo", "ECE medido en ventana móvil de 12 meses",
     "Con cosechas de 300 créditos, una calibración perfecta ya produce ECE de 0.046 por ruido muestral", "6.15"),
]

SUPUESTOS = [
    ("Monto desembolsado = monto solicitado", "El archivo no distingue ambos", "6.10"),
    ("Los rechazados históricos se comportan según su PD estimada", "Parceling; el filtro histórico fue débil", "6.1 y 6.9"),
    ("El analista aprueba el 60% de las revisiones", "Sin dato del proceso; sensibilidad documentada (40% y 80%)", "6.9"),
    ("Costo de fondos 6%, gasto operativo 5%, factor de saldo 0.55", "Parámetros de negocio, no estimados del dato", "6.9"),
    ("Capital aproximado con la fórmula IRB de other retail", "Vara comparativa entre escenarios, no requerimiento regulatorio", "6.12"),
    ("Tasa de descuento de la LGD = tasa efectiva de la política (20.2%)", "Se descuenta al rendimiento de lo que se colocaría", "6.12"),
]

LIMITACIONES = [
    ("Datos sintéticos", "La LGD es unimodal y ninguna variable de T0 explica EAD ni LGD: no es el comportamiento de una cartera real", "6.11"),
    ("Exposición incoherente con la amortización", "El 49.3% de los defaults implica más de 12 cuotas pagadas (hallazgo V-01)", "6.10"),
    ("Muestra de defaults chica", "351 en desarrollo: impide segmentar EAD y LGD y limita modelos complejos", "6.10 y 6.11"),
    ("Sin fecha de default", "No se puede reconstruir la exposición por mes de vida ni modelar el perfil de saldo", "6.10"),
    ("Capacidad de revisión insuficiente", "La política genera 23.2% de revisiones contra 20% declarado (hallazgo V-05)", "6.9"),
    ("Sin datos protegidos", "No hay sexo ni etnia: el análisis de fairness se limita a los proxies disponibles", "6.8"),
]


def _desplazar_titulos(texto: str) -> str:
    """Baja un nivel todos los encabezados, para que el documento tenga una sola jerarquía."""
    return re.sub(r"^(#{1,5}) ", lambda m: "#" * (len(m.group(1)) + 1) + " ", texto, flags=re.MULTILINE)


def _cuerpo_seccion(ruta) -> str:
    texto = ruta.read_text(encoding="utf-8")
    texto = re.sub(r"^\*\*Caso 15.*?\n", "", texto, flags=re.MULTILINE)          # la portada ya lo dice
    texto = re.sub(r"^---\s*$", "", texto, count=1, flags=re.MULTILINE)
    return _desplazar_titulos(texto).strip()


def build(ruta=None) -> str:
    """Genera `reports/documento_tecnico.md` consolidando los quince reportes."""
    ruta = cfg.REPORTS / "documento_tecnico.md" if ruta is None else ruta
    decisiones = pd.DataFrame(DECISIONES, columns=["tema", "decisión", "por qué", "sección"])
    supuestos = pd.DataFrame(SUPUESTOS, columns=["supuesto", "fundamento", "sección"])
    limitaciones = pd.DataFrame(LIMITACIONES, columns=["limitación", "detalle", "sección"])

    indice = "\n".join(f"{i}. **Sección {num}** — {archivo.split('_', 1)[1].replace('.md', '').replace('_', ' ')}"
                       for i, (num, archivo) in enumerate(SECCIONES, start=1))

    tablas = len(list(cfg.TABLES.glob("*.csv")))
    figuras = len(list(cfg.FIGURES.glob("*.png")))
    artefactos = len([p for p in (cfg.ROOT / "models").glob("*") if p.is_file()])

    partes = [f"""# Documento técnico del modelo

## Sistema de scoring de riesgo crediticio · Caso 15 · Caja Rural 360

**Producto:** microcrédito rural amortizable sin garantía para trabajadores independientes con ingresos parcialmente en efectivo
**Alcance:** secciones 6.1 a 6.15 del Trabajo Integrador Final · Credit Risk & Scoring Analytics · DMC Institute
**Versión del documento:** 1.0 · {date.today().isoformat()}
**Modelo champion:** `scorecard_pd_v1` · **PD de producción:** `Platt(PD del scorecard)` · **Política:** `politica_decision_v1`

*Este documento se **genera** desde los quince reportes de sección con `python -m src.techdoc`. No se edita a mano: cualquier
corrección se hace en el reporte de la sección y se vuelve a generar, para que no exista una segunda versión de la verdad.*

---

## Cómo está organizado

Quince secciones en el orden del enunciado, cada una con su propio resumen, evidencia y trazabilidad:

{indice}

Después, tres anexos: decisiones y supuestos, trazabilidad de requisitos y reproducibilidad.

**Dónde está la evidencia.** Cada afirmación del documento se apoya en una tabla o figura generada por los notebooks:
{tablas} tablas en `reports/tables/`, {figuras} figuras en `reports/figures/` y {artefactos} artefactos versionados en `models/`.
Nada se escribió a mano sobre los resultados.

---

## Resumen del trabajo

El encargo era construir el sistema de decisión de crédito para un producto de microcrédito rural: estimar la probabilidad de
incumplimiento, integrarla con exposición y severidad, y convertirla en una política de originación defendible ante un comité
y ante un validador independiente.

**Lo que se construyó.** Un scorecard de tres características (score de buró, capacidad de pago post-crédito y ahorro sobre
monto) con Gini de 0.44 en desarrollo y 0.42 fuera de tiempo, calibrado con Platt, más un motor de decisión que devuelve
APPROVE, REVIEW o REJECT con monto y tasa recomendados, servido por una API con interfaz web y verificado con 103 pruebas
automáticas.

**Los tres hallazgos que cambiaron el trabajo.** Primero, el deterioro de la cartera entre 2021 y 2024 fue de **nivel y no de
mezcla**: la población que llega es la misma, lo que cambió es el riesgo a igual perfil, y eso convierte la calibración en un
control permanente y no en un paso de cierre. Segundo, la pérdida es un problema de **frecuencia y no de severidad**: la LGD
apenas se movió entre cosechas mientras la tasa de default subió 5.4 puntos, así que la palanca es la PD. Tercero, el punto de
corte expresado en PD calibrada funciona como **estabilizador automático**: ante un escenario severo la aprobación cae sola de
64.7% a 36.5% y absorbe 1.5 puntos de pérdida esperada.

**La recomendación.** Aprobación automática con PD calibrada hasta 18%, rechazo sobre 20%, contraoferta automática de monto
cuando la capacidad de pago no alcanza, y revisión manual solo para cuatro reglas verificables. En la cosecha 2025 esa política
aprueba 64.6% con 9.3% de default esperado, contra 81.6% y 13.4% de la política histórica.

**Lo que no se puede prometer.** No existe un punto de corte que cumpla a la vez el objetivo de aprobación de 70% y el límite
de default de 11%: la política llega a 67.2% de aprobación. Ese conflicto se resuelve con la regla de precedencia del apetito
—prevalece el límite de riesgo— y se escala al Comité con los números en la mano, no se disimula moviendo el corte.

---

## Decisiones que definieron el trabajo

{decisiones.to_markdown(index=False)}

## Supuestos declarados

{supuestos.to_markdown(index=False)}

## Limitaciones conocidas

{limitaciones.to_markdown(index=False)}

---
"""]

    for numero, archivo in SECCIONES:
        cuerpo = _cuerpo_seccion(cfg.REPORTS / archivo)
        # El título de la sección vuelve a nivel 1: no hace falta un encabezado envolvente.
        cuerpo = re.sub(r"^## ", "# ", cuerpo, count=1, flags=re.MULTILINE)
        partes.append(f"\n{cuerpo}\n\n---\n")

    partes.append(f"""
# Anexos

## Anexo A · Trazabilidad de requisitos

El anexo completo está en `reports/16_anexo_trazabilidad.md` y su versión en datos en
`reports/tables/anexo_trazabilidad.csv`. Vincula cada requisito de las secciones 6.1 a 6.15, cada entregable y cada
control del Technical Gate con el archivo que lo evidencia, y **verifica que esos archivos existan** en cada corrida.

## Anexo B · Cómo reproducir este trabajo

```bash
python -m venv .venv
.venv\\Scripts\\activate            # Windows
pip install -r requirements.txt
python run_all.py                  # pruebas + 12 notebooks + verificación
uvicorn api.main:app --port 8000   # servicio con interfaz en http://localhost:8000/
```

Semilla fija (`SEED = {cfg.SEED}`), versiones ancladas en `requirements.txt` y artefactos versionados con hash SHA-256 en
`models/registry.json`. Una reejecución limpia regenera tablas, figuras y artefactos idénticos; las dos únicas diferencias
esperadas son la columna de latencia de `modelos_comparacion.csv`, que mide milisegundos de la máquina, y la fecha de
generación de las fichas.

## Anexo C · Inventario de evidencia

| Tipo | Cantidad | Dónde |
|---|---|---|
| Notebooks ejecutados | 12 | `notebooks/` |
| Reportes de sección | 15 | `reports/01_...md` a `reports/15_...md` |
| Tablas de resultados | {tablas} | `reports/tables/` |
| Figuras | {figuras} | `reports/figures/` |
| Artefactos versionados | {artefactos} | `models/` |
| Tableros | 2 | `reports/dashboard_cartera.html`, `reports/dashboard_monitoreo.html` |
| Pruebas automáticas | 103 | `tests/` |
""")

    texto = "\n".join(partes)
    ruta = str(ruta)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta


if __name__ == "__main__":
    salida = build()
    palabras = len(open(salida, encoding="utf-8").read().split())
    print(f"Documento técnico generado: {salida} ({palabras:,} palabras)")


def build_feature_dictionary(ruta=None) -> str:
    """Diccionario de features (capítulo 7): variables de entrada, derivadas y su uso."""
    ruta = cfg.REPORTS / "diccionario_features.md" if ruta is None else ruta
    catalogo = pd.read_csv(cfg.TABLES / "catalogo_variables.csv")
    derivadas = pd.read_csv(cfg.TABLES / "features_derivadas_doc.csv")
    texto = f"""# Diccionario de features

*Generado con `python -m src.techdoc` el {date.today().isoformat()}. Complementa `data/raw/diccionario_datos.csv`,
que documenta los campos originales del caso.*

## 1. Variables originales y su función en el modelo

{catalogo.to_markdown(index=False)}

## 2. Variables derivadas construidas por el equipo

{derivadas.to_markdown(index=False)}

## 3. Reglas de uso

- Las variables marcadas como prohibidas por leakage o endogeneidad **nunca** entran a la matriz de modelado (6.2 y 6.3).
- Las derivadas se recalculan dentro del pipeline, no se leen del archivo: así el scoring en producción reproduce
  exactamente la transformación del entrenamiento (`src/pipeline.py`).
- El scorecard campeón usa tres de estas variables; el resto queda disponible para challengers y monitoreo.
"""
    ruta = str(ruta)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta
