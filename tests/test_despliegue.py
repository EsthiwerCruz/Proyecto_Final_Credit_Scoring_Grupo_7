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
