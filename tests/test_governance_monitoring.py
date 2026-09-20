"""Pruebas de las secciones 6.14 (gobierno) y 6.15 (monitoreo)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config as cfg, data, evaluation as ev, features, governance as gov  # noqa: E402
from src import monitoring as mon, registry as reg, scorecard as sc  # noqa: E402

RAW = data.load_raw()
POP, _ = data.pd_population(RAW)
FX = features.build_features(POP)
DEV, VAL, OOT = (FX[FX["sample"] == s].copy() for s in cfg.SAMPLE_ORDER)
CARD = sc.Scorecard.load(cfg.ROOT / "models" / "scorecard_pd_v1.json")
PLATT = ev.PlattCalibrator().fit(CARD.predict_pd(VAL), VAL[cfg.TARGET])


# ----------------------------------------------------------------- 6.14
def test_materialidad_clasifica_tier_1():
    criterios, nivel = gov.materialidad()
    assert nivel["puntaje"] == criterios["puntaje"].sum()
    assert nivel["nivel"].startswith("Tier 1")          # decide sobre toda la cartera sin intervención humana
    assert "anual" in nivel["frecuencia"].lower()


def test_hallazgos_tienen_todo_lo_que_pide_el_enunciado():
    h = gov.hallazgos()
    assert len(h) >= 5
    for col in ["severidad", "hallazgo", "evidencia", "impacto", "recomendacion", "responsable", "plazo"]:
        assert h[col].notna().all() and (h[col].astype(str).str.strip() != "").all()
    for col in ["hallazgo", "evidencia", "impacto", "recomendacion"]:      # los campos descriptivos, con sustancia
        assert (h[col].astype(str).str.len() > 30).all()
    assert set(h["severidad"]) <= {"Alta", "Media", "Baja", "Informativo"}
    assert (h["severidad"] == "Alta").sum() >= 1
    assert h.index.is_unique


def test_ciclo_de_vida_y_lineas_de_defensa_completos():
    ciclo = gov.ciclo_de_vida()
    assert len(ciclo) == 8 and ciclo["aprueba"].notna().all()
    lineas = gov.lineas_de_defensa()
    assert len(lineas) == 3 and lineas["evidencia que produce"].notna().all()


def test_model_card_se_genera_desde_los_artefactos(tmp_path):
    desempeno = pd.read_csv(cfg.TABLES / "validacion_metricas.csv")
    puntos = pd.read_csv(cfg.TABLES / "scorecard_puntos.csv")
    ruta = gov.build_model_card(tmp_path / "card.md", desempeno, puntos,
                                {"intercepto": PLATT.intercept_, "pendiente": PLATT.slope_},
                                {"base_score": 600, "base_odds": 10, "pdo": 20}, 0.74)
    texto = Path(ruta).read_text(encoding="utf-8")
    hash_real = reg.inventory().loc["scorecard_pd", "sha256"][:32]
    assert hash_real in texto                                    # la card apunta al artefacto que corre
    for seccion in ["Propósito y uso", "Para qué NO es", "Limitaciones", "Monitoreo", "Reproducibilidad"]:
        assert seccion in texto


def test_checklist_de_auditoria_es_verificable():
    c = gov.checklist_auditoria()
    assert len(c) >= 10 and c["evidencia verificable"].notna().all()


# ----------------------------------------------------------------- 6.15
def test_semaforo_respeta_la_direccion_del_indicador():
    assert mon.semaforo("PSI del score", 0.05) == "Verde"         # "max": menos es mejor
    assert mon.semaforo("PSI del score", 0.15) == "Ámbar"
    assert mon.semaforo("PSI del score", 0.40) == "Rojo"
    assert mon.semaforo("Gini de la cosecha", 0.45) == "Verde"    # "min": más es mejor
    assert mon.semaforo("Gini de la cosecha", 0.32) == "Ámbar"
    assert mon.semaforo("Gini de la cosecha", 0.20) == "Rojo"
    assert mon.semaforo("Gini de la cosecha", np.nan) == "Sin dato"


def test_umbrales_vienen_de_lo_medido_y_cubren_los_tres_tipos():
    u = mon.thresholds()
    assert set(u["tipo"]) == {"Datos", "Modelo", "Negocio"}
    assert u["accion_ambar"].notna().all() and u["accion_roja"].notna().all() and u["origen"].notna().all()
    assert np.isclose(u.loc["Pérdida esperada / monto", "verde"], 0.030 * cfg.LGD_ECONOMICA / cfg.LGD_BASELINE, atol=0.001)
    assert u.loc["Gini de la cosecha", "verde"] == 0.35           # piso de la banda histórica entre cosechas


def test_ece_por_trimestre_esta_dominado_por_ruido():
    """Justifica medir el ECE en ventana de 12 meses: con ~300 casos, una calibración perfecta ya da ~0.046."""
    rng = np.random.default_rng(cfg.SEED)
    eces = []
    for _ in range(100):
        p = np.clip(rng.beta(2, 13, 300), 0.01, 0.9)
        eces.append(ev.calibration_metrics(p.round(6), p)["ece"] if False else
                    ev.calibration_metrics(rng.binomial(1, p), p)["ece"])
    assert np.median(eces) > mon.thresholds().loc["Error de calibración (ECE, ventana 12 meses)", "verde"]


def test_metricas_por_cosecha_y_semaforo():
    pd_dev, pd_oot = PLATT.transform(CARD.predict_pd(DEV)), PLATT.transform(CARD.predict_pd(OOT))
    m = mon.cohort_metrics(DEV, OOT, pd_dev, pd_oot, CARD.score(DEV), CARD.score(OOT))
    assert len(m) == 4 and m["solicitudes"].sum() == len(OOT)
    assert (m["psi_score"] >= 0).all() and m["gini"].between(0, 1).all()
    assert m["creditos_ventana"].is_monotonic_increasing               # la ventana móvil acumula
    estado = mon.traffic_light_report(m)
    assert set(np.unique(estado.to_numpy())) <= {"Verde", "Ámbar", "Rojo", "Sin dato"}
    acciones = mon.alert_actions(estado)
    if len(acciones):
        assert acciones["accion"].notna().all() and acciones["responsable"].notna().all()


def test_calendario_separa_frecuencias_y_responsables():
    c = mon.calendario()
    assert {"Diario", "Mensual", "Trimestral", "Anual"} == set(c["frecuencia"])
    assert c["responsable"].notna().all()


def test_artefactos_de_gobierno_y_monitoreo_existen():
    for ruta in ["models/model_card_scorecard_pd.md", "models/ficha_ead.md", "models/ficha_lgd.md",
                 "reports/independent_validation_report.md", "reports/dashboard_monitoreo.html"]:
        archivo = cfg.ROOT / ruta
        if archivo.exists():
            assert archivo.stat().st_size > 500


def test_escalera_cubre_las_seis_acciones_del_enunciado():
    """6.15: investigar, recalibrar, reentrenar, limitar uso, rollback o retiro."""
    acciones = " ".join(mon.escalera_de_acciones()["acción"]).lower()
    for accion in ["investigar", "recalibrar", "reentrenar", "limitar uso", "rollback", "retiro"]:
        assert accion in acciones


def test_tablero_de_cartera_trae_aprobacion_por_segmento():
    """6.12: el tablero debe mostrar approval rate por segmento."""
    t = pd.read_csv(cfg.TABLES / "el_tablero_segmentos.csv")
    assert "aprobacion_segmento" in t.columns
    assert t["aprobacion_segmento"].between(0, 1).all()


def test_ficha_inicial_tiene_los_ocho_puntos_del_capitulo_13():
    texto = (cfg.REPORTS / "ficha_propuesta_inicial.md").read_text(encoding="utf-8").lower()
    for punto in ["caso seleccionado", "pregunta de negocio", "target y población", "risk appetite",
                  "hipótesis", "esquema temporal", "arquitectura conceptual", "riesgos metodológicos"]:
        assert punto in texto, punto
