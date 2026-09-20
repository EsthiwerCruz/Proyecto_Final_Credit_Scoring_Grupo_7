"""Pruebas de empaquetado y despliegue: interfaz web, portabilidad e imagen (6.13)."""
import re
import sys
import unicodedata
from pathlib import Path

from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from api.main import app  # noqa: E402
from src import config as cfg  # noqa: E402

CLIENTE = TestClient(app)


def test_interfaz_web_responde_y_es_autocontenida():
    r = CLIENTE.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    html = r.text
    assert "/score" in html and "Evaluar solicitud" in html
    assert "http://" not in html and "https://" not in html      # sin CDNs: funciona sin internet
    assert "<script" in html and "<style" in html                 # CSS y JS embebidos


def test_endpoint_de_ejemplos_sirve_las_tres_decisiones():
    r = CLIENTE.get("/ejemplos")
    assert r.status_code == 200
    ejemplos = r.json()
    assert set(ejemplos) == {"APPROVE", "REVIEW", "REJECT"}
    for etiqueta, cuerpo in ejemplos.items():
        respuesta = CLIENTE.post("/score", json=cuerpo)
        assert respuesta.status_code == 200
        assert respuesta.json()["decision"] == etiqueta           # el ejemplo hace lo que promete


def test_nombres_de_archivo_generados_son_portables():
    """Un nombre con tilde se corrompe al pasar por Windows: todo lo generado debe ser ASCII."""
    for carpeta in [cfg.TABLES, cfg.FIGURES, cfg.ROOT / "models"]:
        for archivo in carpeta.glob("*"):
            nombre = archivo.name
            assert nombre == unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode(), nombre
            assert " " not in nombre


def test_slug_deja_nombres_seguros():
    assert cfg.slug("Regresión logística (pipeline completo)") == "regresion_logistica_pipeline_completo"
    assert cfg.slug("LightGBM monótono") == "lightgbm_monotono"
    assert re.fullmatch(r"[a-z0-9_]+", cfg.slug("Ñandú  ÁÉÍ/ÓÚ"))


def test_imagen_docker_declara_lo_necesario():
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    for pieza in ["requirements-api.txt", "COPY src/", "COPY api/", "COPY models/", "HEALTHCHECK", "USER scoring"]:
        assert pieza in dockerfile
    requisitos = (RAIZ / "requirements-api.txt").read_text(encoding="utf-8")
    for paquete in ["fastapi", "uvicorn", "pandas", "numpy", "scikit-learn", "scipy"]:
        assert paquete in requisitos
    for pesado in ["lightgbm", "xgboost", "shap", "matplotlib"]:                 # la API no los usa
        assert pesado not in requisitos


def test_gitignore_protege_el_repositorio():
    ignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    for patron in [".venv/", "__pycache__/", ".pytest_cache/", ".env"]:
        assert patron in ignore


def test_infraestructura_y_flujos_de_ci_presentes():
    bicep = (RAIZ / "deploy" / "azure" / "main.bicep").read_text(encoding="utf-8")
    for recurso in ["Microsoft.ContainerRegistry", "Microsoft.App/managedEnvironments",
                    "Microsoft.App/containerApps", "/health"]:
        assert recurso in bicep
    for script in ["deploy.sh", "deploy.ps1"]:
        assert (RAIZ / "deploy" / "azure" / script).exists()
    for flujo in ["tests.yml", "deploy-azure.yml"]:
        assert (RAIZ / ".github" / "workflows" / flujo).exists()


# --------------------------------------------------------------- Anexo y documento técnico
def test_anexo_verifica_la_evidencia_que_cita():
    from src import traceability as tz

    f = tz.build_frames()
    req, gate = f["requisitos"], f["gate"]
    assert len(req) >= 50 and len(f["entregables"]) == 10 and len(gate) == 5
    assert (req["estado"] == "Cumple").all(), req[req.estado != "Cumple"]["evidencia"].tolist()
    assert (gate["estado"] == "Cumple").all(), gate[gate.estado != "Cumple"]["evidencia"].tolist()
    # Toda sección 6.1 a 6.15 aparece al menos una vez
    bloques = {b.split()[0] for b in req["bloque"]}
    assert {f"6.{i}" for i in range(1, 16)} <= bloques


def test_documento_tecnico_consolida_las_quince_secciones():
    import re as _re

    ruta = RAIZ / "reports" / "documento_tecnico.md"
    if not ruta.exists():
        return
    texto = ruta.read_text(encoding="utf-8")
    for n in range(1, 16):
        assert _re.search(rf"^# 6\.{n}[ ·]", texto, flags=_re.M), f"falta la sección 6.{n}"
    assert len(texto.split()) > 20000                       # documento completo, no un índice
    assert "Decisiones que definieron el trabajo" in texto
    assert "Supuestos declarados" in texto and "Limitaciones conocidas" in texto
    assert not _re.search(r"^# Sección 6\.\d+\n\n## 6\.", texto, flags=_re.M)   # sin títulos duplicados


def test_informe_ejecutivo_cita_las_cifras_de_los_artefactos():
    """El informe se genera desde los artefactos: sus cifras tienen que coincidir con ellos."""
    import json

    ruta = RAIZ / "reports" / "informe_ejecutivo.md"
    if not ruta.exists():
        return
    texto = ruta.read_text(encoding="utf-8")
    pol = json.loads((RAIZ / "models" / "politica_decision_v1.json").read_text(encoding="utf-8"))
    r25 = pol["resultados_2025_oot"]
    assert f"{r25['aprobacion_final_esperada']:.1%}" in texto
    assert f"{r25['default_cartera_final']:.1%}" in texto
    for bloque in ["Resumen ejecutivo", "Decisiones que pedimos al Comité", "El caso económico",
                   "Riesgos y condiciones para el uso", "Glosario"]:
        assert bloque in texto
    assert len(texto.split()) > 3500                      # informe completo, no un resumen
    assert texto.count("![") >= 5                          # con evidencia visual


def test_informe_ejecutivo_separa_seleccion_de_precio():
    """La caída de resultado se descompone: riesgo por un lado, decisión comercial por el otro."""
    from src.execreport import _caso_economico

    e = _caso_economico()
    resultado_hist = e["margen_hist"] - e["el_hist"]
    resultado_tasa_hist = e["margen_nuevo_tasa_hist"] - e["el_nuevo"]
    resultado_nuevo = e["margen_nuevo"] - e["el_nuevo"]
    assert e["el_nuevo"] / e["monto_nuevo"] < e["el_hist"] / e["monto_hist"]     # menos pérdida por sol prestado
    assert resultado_tasa_hist < resultado_hist                                   # el volumen cuesta
    assert resultado_nuevo < resultado_tasa_hist                                  # el precio cuesta aparte
