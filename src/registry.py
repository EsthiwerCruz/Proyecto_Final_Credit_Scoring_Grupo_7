"""Model Registry: inventario, versionado, promoción y rollback (sección 6.13).

Un registro de modelos no necesita una plataforma para existir: necesita que **cada
artefacto tenga versión, dueño, estado y huella verificable**, y que se pueda responder
en cualquier momento "qué modelo respondió esta solicitud".

El registro vive en `models/registry.json` y guarda, por artefacto, el SHA-256 del
archivo. Si alguien reemplaza un artefacto sin registrar el cambio, la verificación falla:
es el control mínimo de integridad que pide una validación independiente.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

import pandas as pd

from . import config as cfg

REGISTRY_PATH = cfg.ROOT / "models" / "registry.json"

ESTADOS = ("champion", "challenger", "soporte", "retirado")


def file_hash(ruta) -> str:
    """SHA-256 del artefacto: la huella que permite detectar un cambio no registrado."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


def register(nombre: str, archivo: str, version: str, estado: str, seccion: str, descripcion: str,
             dueño: str = "Equipo de Credit Risk Analytics", entrenado_con: str = "DEV 2021-2023",
             registry_path=REGISTRY_PATH) -> dict:
    """Agrega o actualiza una entrada del registro y devuelve el registro completo."""
    assert estado in ESTADOS, f"estado inválido: {estado}"
    ruta = cfg.ROOT / "models" / archivo
    registro = load(registry_path)
    entrada = {"nombre": nombre, "archivo": archivo, "version": version, "estado": estado,
               "seccion": seccion, "descripcion": descripcion, "dueño": dueño,
               "entrenado_con": entrenado_con, "registrado_el": date.today().isoformat(),
               "sha256": file_hash(ruta), "bytes": ruta.stat().st_size}
    registro["modelos"] = [m for m in registro.get("modelos", []) if m["nombre"] != nombre] + [entrada]
    registro["modelos"].sort(key=lambda m: (m["estado"], m["nombre"]))
    save(registro, registry_path)
    return registro


def load(registry_path=REGISTRY_PATH) -> dict:
    if not registry_path.exists():
        return {"entorno": "Development", "modelos": []}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def save(registro: dict, registry_path=REGISTRY_PATH) -> None:
    registry_path.parent.mkdir(exist_ok=True)
    registry_path.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


def inventory(registry_path=REGISTRY_PATH) -> pd.DataFrame:
    """Inventario de modelos, que es además el insumo del gobierno (6.14)."""
    registro = load(registry_path)
    if not registro.get("modelos"):
        return pd.DataFrame(columns=["nombre", "version", "estado", "seccion", "archivo", "sha256"])
    return pd.DataFrame(registro["modelos"]).set_index("nombre")


def verify(registry_path=REGISTRY_PATH) -> pd.DataFrame:
    """Compara el hash registrado contra el archivo en disco. Cualquier 'False' es un incidente."""
    filas = []
    for m in load(registry_path).get("modelos", []):
        ruta = cfg.ROOT / "models" / m["archivo"]
        existe = ruta.exists()
        filas.append({"nombre": m["nombre"], "archivo": m["archivo"], "existe": existe,
                      "hash_coincide": bool(existe and file_hash(ruta) == m["sha256"])})
    return pd.DataFrame(filas).set_index("nombre")


def promote(nombre: str, registry_path=REGISTRY_PATH) -> pd.DataFrame:
    """Promueve un challenger a champion y degrada al champion anterior a challenger.

    El rollback es la misma operación en sentido inverso: por eso el modelo anterior no se
    borra ni se sobrescribe, se degrada. Volver atrás es promover de nuevo al anterior.
    """
    registro = load(registry_path)
    actual = [m for m in registro["modelos"] if m["estado"] == "champion"]
    for m in registro["modelos"]:
        if m["nombre"] == nombre:
            m["estado"] = "champion"
        elif m in actual:
            m["estado"] = "challenger"
    registro["ultimo_cambio"] = {"accion": "promocion", "modelo": nombre, "fecha": date.today().isoformat(),
                                 "champion_anterior": actual[0]["nombre"] if actual else None}
    save(registro, registry_path)
    return inventory(registry_path)


# ---------------------------------------------------------------------------
# Disparadores de recalibración y reentrenamiento
# ---------------------------------------------------------------------------
TRIGGERS = [
    ("Calibración", "Observado / predicho de la cosecha fuera de [0.85, 1.15] dos meses seguidos",
     "Recalibrar Platt con la ventana más reciente", "6.7"),
    ("Calibración", "Pérdida esperada de la cosecha por encima de 3.34% (verde restateado)",
     "Revisar calibración antes que el punto de corte", "6.12"),
    ("Discriminación", "Gini de la cosecha por debajo de 0.30 (piso de la banda histórica 0.35-0.49)",
     "Investigar; si persiste dos cosechas, reentrenar", "6.7"),
    ("Estabilidad", "PSI del score por encima de 0.10, o de una variable del scorecard por encima de 0.25",
     "Investigar el cambio de mezcla; reentrenar si es estructural", "6.7"),
    ("Población", "Tasa de faltantes de buró o ingreso por encima del doble de lo histórico",
     "Revisar la fuente antes de tocar el modelo", "6.3"),
    ("Severidad", "LGD o factor de exposición de la cosecha fuera de ±5 pp de lo estimado",
     "Reestimar EAD y LGD y actualizar la capa de Expected Loss", "6.10 y 6.11"),
    ("Fairness", "AIR por región o por ingreso en efectivo por debajo de 0.80 dos meses seguidos",
     "Revisar la política de verificación; escalar al Comité", "6.8"),
    ("Negocio", "Cola de revisión manual por encima del 20% de las solicitudes",
     "Priorizar por valor esperado y evaluar capacidad", "6.9"),
]


def triggers_table() -> pd.DataFrame:
    return pd.DataFrame(TRIGGERS, columns=["dimensión", "disparador", "acción", "sección"])
