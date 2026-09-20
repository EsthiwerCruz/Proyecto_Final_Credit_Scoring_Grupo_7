"""Ejecuta el proyecto completo de punta a punta y verifica que todo quede consistente.

Uso (desde la raíz del repositorio):

    python run_all.py                  # pruebas + los 11 notebooks en orden + verificación
    python run_all.py --tests          # solo las pruebas automáticas (30 segundos)
    python run_all.py --notebooks      # solo los notebooks
    python run_all.py --desde 04       # retoma desde el notebook 04 en adelante
    python run_all.py --documentos     # solo regenerar informe ejecutivo, documento técnico y anexo
    python run_all.py --verificar      # solo la verificación de artefactos y registro

Orden de dependencias: el notebook 03 deja el scorecard en `models/`, el 04 deja el
challenger y el 05 el calibrador; del 04 en adelante cada uno necesita lo que dejó el
anterior. Por eso se ejecutan en orden y el script se detiene en el primer error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
NOTEBOOKS = [
    ("00_negocio_y_poblacion", "6.1 y 6.2 · negocio, población y split temporal"),
    ("01_calidad_y_features", "6.3 · calidad, faltantes y variables derivadas"),
    ("02_eda_riesgo", "6.4 · EDA orientado a riesgo"),
    ("03_scorecard_pd", "6.5 · scorecard tradicional (deja models/scorecard_pd_v1.json)"),
    ("04_modelos_pd", "6.6 · champion/challenger (deja models/challenger_lgbm_v1.joblib)"),
    ("05_validacion_calibracion", "6.7 · validación y calibración (deja models/calibrador_platt_v1.json)"),
    ("06_explainability_fairness", "6.8 · explicabilidad y fair lending"),
    ("07_decision_engine", "6.9 · motor de decisión (deja models/politica_decision_v1.json)"),
    ("08_ead_lgd", "6.10 y 6.11 · EAD y LGD (deja models/ead_lgd_v1.json)"),
    ("09_expected_loss_stress", "6.12 · expected loss, tablero y stress"),
    ("10_api_arquitectura", "6.13 · arquitectura, API y MLOps"),
    ("11_gobierno_monitoreo", "6.14 y 6.15 · gobierno, Model Card, validación y monitoreo"),
]


def _correr(comando: list[str], descripcion: str) -> float:
    print(f"\n▶ {descripcion}")
    t0 = time.perf_counter()
    resultado = subprocess.run(comando, cwd=RAIZ)
    segundos = time.perf_counter() - t0
    if resultado.returncode != 0:
        print(f"✗ Falló: {descripcion} (código {resultado.returncode})")
        sys.exit(resultado.returncode)
    print(f"✓ Listo en {segundos:.0f} s")
    return segundos


def correr_tests() -> None:
    _correr([sys.executable, "-m", "pytest", "tests", "-q"], "Pruebas automáticas")


def correr_notebooks(desde: str | None = None) -> None:
    pendientes = NOTEBOOKS
    if desde:
        indices = [i for i, (n, _) in enumerate(NOTEBOOKS) if n.startswith(desde)]
        if not indices:
            print(f"No hay notebook que empiece con '{desde}'")
            sys.exit(1)
        pendientes = NOTEBOOKS[indices[0]:]
    total = 0.0
    for nombre, descripcion in pendientes:
        ruta = RAIZ / "notebooks" / f"{nombre}.ipynb"
        total += _correr([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
                          "--inplace", "--ExecutePreprocessor.timeout=1800", str(ruta)],
                         f"{nombre} · {descripcion}")
    print(f"\nTiempo total de notebooks: {total/60:.1f} minutos")


def generar_documentos() -> None:
    """Regenera informe ejecutivo, documento técnico y anexo desde los artefactos y los reportes."""
    sys.path.insert(0, str(RAIZ))
    from src import execreport, techdoc, traceability  # noqa: PLC0415

    print("\n▶ Documentos consolidados")
    print("  informe ejecutivo:", Path(execreport.build()).relative_to(RAIZ))
    print("  documento técnico:", Path(techdoc.build()).relative_to(RAIZ))
    print("  diccionario de features:", Path(techdoc.build_feature_dictionary()).relative_to(RAIZ))
    print("  anexo:", Path(traceability.build_annex()).relative_to(RAIZ))


def verificar() -> None:
    """Comprueba que los artefactos existan, que el registro no esté alterado y que el servicio responda."""
    sys.path.insert(0, str(RAIZ))
    from src import registry as reg  # noqa: PLC0415

    print("\n▶ Verificación de artefactos y registro")
    verificacion = reg.verify()
    print(verificacion.to_string())
    if not bool(verificacion["hash_coincide"].all()):
        print("✗ Hay artefactos que no coinciden con el registro. Vuelve a registrar o revisa el cambio.")
        sys.exit(1)

    salidas = {"Tablas": len(list((RAIZ / "reports" / "tables").glob("*.csv"))),
               "Figuras": len(list((RAIZ / "reports" / "figures").glob("*.png"))),
               "Reportes": len(list((RAIZ / "reports").glob("*.md"))),
               "Tablero": (RAIZ / "reports" / "dashboard_cartera.html").exists()}
    print("\nSalidas generadas:", salidas)

    from fastapi.testclient import TestClient  # noqa: PLC0415
    from api.main import app  # noqa: PLC0415

    cliente = TestClient(app)
    salud = cliente.get("/health").json()
    print("Servicio de scoring:", salud["estado"], "· artefactos íntegros:", all(salud["integridad"].values()))
    print("\n✓ Todo consistente. El proyecto está reproducido de punta a punta.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecuta el proyecto completo")
    parser.add_argument("--tests", action="store_true", help="solo las pruebas")
    parser.add_argument("--notebooks", action="store_true", help="solo los notebooks")
    parser.add_argument("--documentos", action="store_true", help="solo regenerar anexo y documento técnico")
    parser.add_argument("--verificar", action="store_true", help="solo la verificación final")
    parser.add_argument("--desde", type=str, default=None, help="retomar desde un notebook (por ejemplo 04)")
    args = parser.parse_args()

    todo = not (args.tests or args.notebooks or args.verificar or args.documentos)
    inicio = time.perf_counter()
    if args.tests or todo:
        correr_tests()
    if args.notebooks or todo or args.desde:
        correr_notebooks(args.desde)
    if args.documentos or todo:
        generar_documentos()
    if args.verificar or todo:
        verificar()
    print(f"\nTiempo total: {(time.perf_counter() - inicio)/60:.1f} minutos")
