"""Pruebas del servicio de scoring y del Model Registry (sección 6.13)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from api.main import app, motor  # noqa: E402
from src import config as cfg, data, features, registry as reg  # noqa: E402

CLIENTE = TestClient(app)
RAW = data.load_raw()
BASE = {"application_id": "TEST-001", "age": 38, "region": "Sur", "channel": "agencia",
        "employment_type": "independiente", "monthly_income": 3200.0, "employment_tenure_months": 60.0,
        "bureau_score": 712.0, "prior_delinquencies_24m": 0, "bureau_inquiries_6m": 1, "active_loans": 1,
        "monthly_debt_payment": 400.0, "savings_balance": 2500.0, "new_customer_flag": 0,
        "relationship_months": 36.0, "requested_amount": 8000.0, "term_months": 24,
        "distance_to_branch_km": 12.0, "household_dependents": 2, "cash_income_share": 0.55}


def test_health_verifica_integridad_de_los_artefactos():
    r = CLIENTE.get("/health").json()
    assert r["estado"] == "ok"
    assert all(r["integridad"].values())            # ningún artefacto alterado fuera del registro
    assert "scorecard_pd" in r["integridad"]


def test_score_devuelve_el_contrato_minimo_del_enunciado():
    r = CLIENTE.post("/score", json=BASE)
    assert r.status_code == 200
    d = r.json()
    for campo in ["application_id", "pd", "score", "risk_band", "decision", "reason_codes",
                  "recommended_amount_or_limit", "recommended_rate"]:
        assert campo in d
    assert 0 < d["pd"] < 1 and 400 < d["score"] < 900
    assert d["decision"] in ("APPROVE", "REVIEW", "REJECT")
    assert d["trace_id"] and d["modelo"]["scorecard"] == "scorecard_pd_v1"


def test_validacion_de_rangos_columnas_y_coherencia():
    casos = [dict(BASE, bureau_score=1200.0), {k: v for k, v in BASE.items() if k != "requested_amount"},
             dict(BASE, monthly_debt_payment=99_000.0), dict(BASE, term_months=120), dict(BASE, age=12)]
    for cuerpo in casos:
        assert CLIENTE.post("/score", json=cuerpo).status_code == 422


def test_faltantes_permitidos_se_resuelven_por_politica():
    """Sin score de buró o sin ingreso la API responde y manda a revisión, nunca rechaza en automático."""
    for campo in ("bureau_score", "monthly_income"):
        d = CLIENTE.post("/score", json=dict(BASE, **{campo: None})).json()
        assert d["decision"] == "REVIEW"
        assert any("no disponible" in r or "no informado" in r for r in d["reason_codes"]) or d["motivo"]


def test_la_api_responde_lo_mismo_que_el_desarrollo():
    """Sin train-serve skew: mismo PD, score y decisión que calculan los módulos."""
    ttd = features.build_features(RAW[RAW[cfg.DATE_COL].dt.year == 2025]).sample(50, random_state=cfg.SEED)
    enteros = ["age", "prior_delinquencies_24m", "bureau_inquiries_6m", "active_loans",
               "new_customer_flag", "term_months", "household_dependents"]
    cuerpos = []
    for _, fila in ttd.iterrows():
        d = {}
        for c in BASE:
            v = fila[c]
            d[c] = None if pd.isna(v) else (str(v) if c == "application_id" else
                                            int(v) if c in enteros else
                                            float(v) if isinstance(v, (np.integer, np.floating)) else v)
        cuerpos.append(d)
    r = CLIENTE.post("/score/batch", json={"solicitudes": cuerpos})
    assert r.status_code == 200
    api = pd.DataFrame(r.json()["resultados"]).set_index("application_id")
    pd_dev = motor.pd_calibrada(ttd)
    dec_dev = motor.politica.decide(ttd, pd_dev, recalcular_pd=motor.pd_calibrada)
    idx = ttd["application_id"].astype(str)
    assert (api.loc[idx, "score"].to_numpy() == motor.card.score(ttd)).all()
    assert np.allclose(api.loc[idx, "pd"].to_numpy(), np.round(pd_dev, 4))
    assert (api.loc[idx, "decision"].to_numpy() == dec_dev["decision"].to_numpy()).all()


def test_registro_inventario_promocion_y_rollback(tmp_path):
    ruta = tmp_path / "registry.json"
    ruta.write_text(reg.REGISTRY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    assert (reg.verify()["hash_coincide"]).all()
    inv = reg.inventory(ruta)
    assert (inv["estado"] == "champion").sum() == 1
    reg.promote("challenger_lgbm", ruta)
    assert reg.inventory(ruta).loc["challenger_lgbm", "estado"] == "champion"
    assert reg.inventory(ruta).loc["scorecard_pd", "estado"] == "challenger"
    reg.promote("scorecard_pd", ruta)                                   # rollback
    assert reg.inventory(ruta).loc["scorecard_pd", "estado"] == "champion"


def test_disparadores_cubren_las_dimensiones_de_monitoreo():
    t = reg.triggers_table()
    assert {"Calibración", "Discriminación", "Estabilidad", "Fairness"} <= set(t["dimensión"])
    assert t["acción"].notna().all() and t["sección"].notna().all()
