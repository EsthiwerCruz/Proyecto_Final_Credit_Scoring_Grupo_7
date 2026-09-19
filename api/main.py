"""Servicio de scoring de Caja Rural 360 (sección 6.13).

Expone la decisión de crédito con el mismo código que usan los notebooks: el scorecard de
6.5, el calibrador de 6.7 y el motor de decisión de 6.9. Si el servicio respondiera algo
distinto de lo que calcula el desarrollo, habría *train-serve skew*; por eso la API no
reimplementa nada, importa los mismos módulos y carga los mismos artefactos versionados.

Levantar en local:

    uvicorn api.main:app --reload --port 8000

Endpoints:

* `GET  /health`   estado del servicio y artefactos cargados con su versión y hash
* `GET  /version`  inventario del Model Registry y política vigente
* `POST /score`    decisión de una solicitud
* `POST /score/batch`  hasta 500 solicitudes en una llamada
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, decision as dec, features, portfolio as pf  # noqa: E402
from src import registry as reg, scorecard as sc  # noqa: E402

API_VERSION = "1.0.0"
MODELOS = cfg.ROOT / "models"

app = FastAPI(
    title="Caja Rural 360 · Servicio de scoring",
    version=API_VERSION,
    description=(
        "Decide una solicitud de microcrédito rural: **PD calibrada**, score, banda, decisión "
        "(APPROVE / REVIEW / REJECT), razones, monto recomendado y tasa por riesgo.\n\n"
        "El servicio no reimplementa nada: usa los mismos módulos y artefactos versionados que el desarrollo "
        "(scorecard de 6.5, calibrador de 6.7 y política de 6.9).\n\n"
        "**Interfaz interactiva en `/`** · Contrato y ejemplos abajo."),
    openapi_tags=[{"name": "Scoring", "description": "Decisión de crédito"},
                  {"name": "Operación", "description": "Estado, versiones e integridad de artefactos"}],
)
ESTATICOS = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# Contrato de entrada: las 19 columnas del pipeline de 6.3, con rangos validados
# ---------------------------------------------------------------------------
class Solicitud(BaseModel):
    application_id: str = Field(..., description="Identificador de la solicitud")
    age: int = Field(..., ge=18, le=100)
    region: str
    channel: str
    employment_type: str
    monthly_income: float | None = Field(None, ge=0, description="Nulo si el cliente no lo declara")
    employment_tenure_months: float = Field(..., ge=0, le=600)
    bureau_score: float | None = Field(None, ge=300, le=900, description="Nulo si el buró no devuelve score")
    prior_delinquencies_24m: int = Field(..., ge=0, le=20)
    bureau_inquiries_6m: int = Field(..., ge=0, le=30)
    active_loans: int = Field(..., ge=0, le=20)
    monthly_debt_payment: float = Field(..., ge=0)
    savings_balance: float | None = Field(None, ge=0)
    new_customer_flag: int = Field(..., ge=0, le=1)
    relationship_months: float = Field(..., ge=0, le=600)
    requested_amount: float = Field(..., gt=0, le=200_000)
    term_months: int = Field(..., ge=3, le=60)
    distance_to_branch_km: float = Field(..., ge=0, le=500)
    household_dependents: int = Field(..., ge=0, le=15)
    cash_income_share: float = Field(..., ge=0, le=1)

    model_config = {"json_schema_extra": {"examples": [{
        "application_id": "SOL-0001", "age": 38, "region": "Sur", "channel": "agencia",
        "employment_type": "independiente", "monthly_income": 3200, "employment_tenure_months": 60,
        "bureau_score": 712, "prior_delinquencies_24m": 0, "bureau_inquiries_6m": 1, "active_loans": 1,
        "monthly_debt_payment": 400, "savings_balance": 2500, "new_customer_flag": 0,
        "relationship_months": 36, "requested_amount": 8000, "term_months": 24,
        "distance_to_branch_km": 12, "household_dependents": 2, "cash_income_share": 0.55}]}}

    @field_validator("region", "channel", "employment_type")
    @classmethod
    def no_vacio(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("no puede ser vacío")
        return v

    @field_validator("monthly_debt_payment")
    @classmethod
    def deuda_razonable(cls, v: float, info) -> float:
        ingreso = info.data.get("monthly_income")
        if ingreso is not None and ingreso > 0 and v > ingreso:
            raise ValueError("la cuota de deudas vigentes no puede superar el ingreso declarado")
        return v


class Lote(BaseModel):
    solicitudes: list[Solicitud] = Field(..., max_length=500)


class Respuesta(BaseModel):
    application_id: str
    pd: float
    score: int
    risk_band: str
    decision: str
    reason_codes: list[str]
    recommended_amount_or_limit: float | None
    recommended_rate: float | None
    motivo: str
    expected_loss: float | None
    modelo: dict
    trace_id: str
    latencia_ms: float


# ---------------------------------------------------------------------------
# Carga de artefactos (una sola vez, al arrancar)
# ---------------------------------------------------------------------------
class Motor:
    """Encapsula los artefactos y la lógica de scoring, para que la API no tenga reglas propias."""

    def __init__(self):
        self.card = sc.Scorecard.load(MODELOS / "scorecard_pd_v1.json")
        self.calibrador = json.loads((MODELOS / "calibrador_platt_v1.json").read_text(encoding="utf-8"))["calibrador"]
        self.politica = dec.DecisionPolicy()
        self.registro = reg.load()
        self.cargado_el = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def pd_calibrada(self, df: pd.DataFrame) -> np.ndarray:
        """PD del scorecard corregida con el Platt de 6.7: a + b·logit(PD)."""
        p = np.clip(self.card.predict_pd(df), 1e-6, 1 - 1e-6)
        z = self.calibrador["intercepto"] + self.calibrador["pendiente"] * np.log(p / (1 - p))
        return 1 / (1 + np.exp(-z))

    def banda(self, score: float) -> str:
        cortes = [(640, "A"), (620, "B"), (600, "C"), (580, "D"), (560, "E")]
        for corte, letra in cortes:
            if score > corte:
                return letra
        return "F"

    def decidir(self, df: pd.DataFrame) -> pd.DataFrame:
        pd_hat = self.pd_calibrada(df)
        d = self.politica.decide(df, pd_hat, recalcular_pd=self.pd_calibrada)
        d["score"] = self.card.score(df)
        d["risk_band"] = [self.banda(s) for s in d["score"]]
        d["reason_codes"] = self.card.reason_codes(df, n=3)
        el = pf.expected_loss_frame(df, d["pd_calibrada"].to_numpy(),
                                    monto=d["monto_recomendado"].fillna(0).to_numpy(),
                                    lgd=cfg.LGD_ECONOMICA)
        d["expected_loss"] = np.where(d["decision"].eq(dec.REJECT), np.nan, el["el"])
        return d


motor = Motor()


def _a_frame(solicitudes: list[Solicitud]) -> pd.DataFrame:
    df = pd.DataFrame([s.model_dump() for s in solicitudes]).set_index("application_id", drop=False)
    return features.build_features(df)


def _respuestas(df_original: pd.DataFrame, decisiones: pd.DataFrame, t0: float) -> list[dict]:
    latencia = (time.perf_counter() - t0) * 1000 / max(len(decisiones), 1)
    modelo = {"scorecard": "scorecard_pd_v1", "calibrador": "calibrador_platt_v1",
              "politica": "politica_decision_v1", "api": API_VERSION}
    salida = []
    for idx, fila in decisiones.iterrows():
        salida.append({
            "application_id": str(df_original.loc[idx, "application_id"]),
            "pd": round(float(fila["pd_calibrada"]), 4),
            "score": int(fila["score"]),
            "risk_band": fila["risk_band"],
            "decision": fila["decision"],
            "reason_codes": list(fila["reason_codes"]),
            "recommended_amount_or_limit": (None if pd.isna(fila["monto_recomendado"])
                                            else round(float(fila["monto_recomendado"]), 2)),
            "recommended_rate": (None if pd.isna(fila["tasa_recomendada"])
                                 else round(float(fila["tasa_recomendada"]), 4)),
            "motivo": fila["motivo"],
            "expected_loss": (None if pd.isna(fila["expected_loss"]) else round(float(fila["expected_loss"]), 2)),
            "modelo": modelo,
            "trace_id": str(uuid.uuid4()),
            "latencia_ms": round(latencia, 3),
        })
    return salida


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def interfaz() -> str:
    """Interfaz web para evaluar una solicitud sin escribir JSON."""
    return (ESTATICOS / "index.html").read_text(encoding="utf-8")


@app.get("/ejemplos", tags=["Scoring"])
def ejemplos() -> dict:
    """Tres solicitudes reales de la cosecha 2025, una por cada salida del motor."""
    ruta = cfg.TABLES / "api_ejemplos.json"
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="Ejecuta el notebook 10 para generar los ejemplos")
    return json.loads(ruta.read_text(encoding="utf-8"))["requests"]


@app.get("/health", tags=["Operación"])
def health() -> dict:
    verificacion = reg.verify()
    return {"estado": "ok" if bool(verificacion["hash_coincide"].all()) else "artefactos alterados",
            "api": API_VERSION, "artefactos_cargados_el": motor.cargado_el,
            "integridad": verificacion["hash_coincide"].to_dict(),
            "entorno": motor.registro.get("entorno", "Development")}


@app.get("/version", tags=["Operación"])
def version() -> dict:
    inv = reg.inventory()
    return {"api": API_VERSION,
            "modelos": inv.reset_index()[["nombre", "version", "estado", "seccion"]].to_dict("records"),
            "politica": {"pd_approve_max": motor.politica.pd_approve_max,
                         "pd_reject_min": motor.politica.pd_reject_min,
                         "dti_auto_max": motor.politica.dti_auto_max,
                         "monto_revision": motor.politica.amount_auto_max},
            "calibrador": motor.calibrador}


@app.post("/score", response_model=Respuesta, tags=["Scoring"])
def score(solicitud: Solicitud) -> dict:
    t0 = time.perf_counter()
    try:
        df = _a_frame([solicitud])
        decisiones = motor.decidir(df)
    except Exception as e:                                  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"No se pudo puntuar la solicitud: {e}") from e
    return _respuestas(df, decisiones, t0)[0]


@app.post("/score/batch", tags=["Scoring"])
def score_batch(lote: Lote) -> dict:
    if not lote.solicitudes:
        raise HTTPException(status_code=422, detail="El lote no puede venir vacío")
    t0 = time.perf_counter()
    df = _a_frame(lote.solicitudes)
    decisiones = motor.decidir(df)
    resultados = _respuestas(df, decisiones, t0)
    mezcla = decisiones["decision"].value_counts(normalize=True).round(4).to_dict()
    return {"solicitudes": len(resultados), "mezcla_de_decisiones": mezcla, "resultados": resultados}
