"""Configuración central del proyecto (Caso 15 - Caja Rural 360).

Constantes que definen target, población, esquema temporal y parámetros de
política, para que notebooks y tests usen exactamente la misma versión.
"""
import re
import unicodedata
from pathlib import Path

# --- Rutas -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
RAW_DATA_FILE = DATA_RAW / "data.csv"
DICTIONARY_FILE = DATA_RAW / "diccionario_datos.csv"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
TABLES = REPORTS / "tables"

SEED = 42

# --- Campos estructurales ----------------------------------------------------
ID_COL = "application_id"
DATE_COL = "observation_date"
TARGET = "default_12m_flag"
OUTCOME_FILTER = "outcome_available_flag"
APPROVED_FLAG = "approved_flag"

# --- Definición de default (oficial, sección 5.2 del enunciado) -------------
DEFAULT_DPD_THRESHOLD = 90
PERFORMANCE_WINDOW_MONTHS = 12

# --- Esquema temporal (sección 6.2) ------------------------------------------
# Años calendario completos: muestras comparables y trazables por cosecha anual.
# No se detectó estacionalidad del default (ver quality.seasonality_test), así
# que el corte no depende de ella. Límites inclusivos sobre observation_date.
TEMPORAL_SPLITS = {
    "DEV": ("2021-01-01", "2023-12-31"),
    "VAL": ("2024-01-01", "2024-12-31"),
    "OOT": ("2025-01-01", "2025-12-31"),
}
SAMPLE_ORDER = ["DEV", "VAL", "OOT"]

# Subperiodos de DEV para comprobar que el signo de una variable no se invierte
# dentro del propio desarrollo (regla R2 de la pre-selección de 6.3).
DEV_SUBPERIODS = {
    "DEV_2021_2022": ("2021-01-01", "2022-12-31"),
    "DEV_2023": ("2023-01-01", "2023-12-31"),
}

# --- Pre-selección de variables derivadas (sección 6.3) ----------------------
# Se decide SOLO con DEV. VAL se reporta como información y OOT no se consulta
# (se reserva para la evaluación final, como fija 6.2).
SCREEN_ALPHA_SIGNAL = 0.05        # R1: señal univariada en DEV (Mann-Whitney)
SCREEN_ALPHA_INCREMENTAL = 0.10   # R3: aporte sobre sus propios componentes (test de razón de verosimilitud)
SCREEN_ALPHA_FAIRNESS = 0.05      # R4: necesidad de negocio de un componente sensible
SCREEN_REDUNDANCY_RHO = 0.70      # R5: redundancia entre derivadas (Spearman)
# Núcleo de riesgo contra el que se mide el aporte incremental.
SCREEN_CORE = ["bureau_score", "dti"]

# Control de madurez: cosechas OOT con 12 meses de ventana ya cumplidos a la
# fecha de elaboración (setiembre 2026).
OOT_MATURE_END = "2025-08-31"

# --- Parámetros de negocio usados en el Risk Appetite (sección 6.1) ----------
MICRO_MAX_AUTO_AMOUNT = 20_000   # S/ ; tope de aprobación automática
MAX_AMOUNT_HARD = 30_000         # S/ ; por encima -> otro producto
REMOTE_DISTANCE_KM = 50
HIGH_CASH_SHARE = 0.80
LONG_TERM_MONTHS = 36
# TEA de referencia del producto (~ mediana histórica) para estimar la cuota
# sin usar la tasa ofrecida, que es endógena al riesgo.
REFERENCE_ANNUAL_RATE = 0.30
DTI_POST_AUTO_MAX = 0.45         # capacidad de pago: aprobación automática
DTI_POST_HARD_MAX = 0.60         # por encima -> solo con ajuste de monto/plazo


# --- Economía del producto (supuestos de 6.9, documentados en el reporte) -----
COST_OF_FUNDS = 0.06          # TEA de fondeo
OPERATING_COST_RATE = 0.05    # gasto operativo anual sobre saldo promedio
AVG_BALANCE_FACTOR = 0.55     # saldo promedio / monto desembolsado en un crédito francés
EAD_FACTOR_BASELINE = 0.415   # factor de exposición estimado en 6.10 (baseline global, defaults de DEV)
LGD_BASELINE = 0.616          # LGD contable estimada en 6.11 (baseline global, defaults de DEV)
LGD_ECONOMICA = 0.686         # LGD descontada a la tasa efectiva de la política (6.12): base adoptada para EL
LGD_ECONOMICA_10 = 0.654      # sensibilidad: la misma LGD descontada al 10% anual (6.11)
LGD_DOWNTURN = 0.626          # peor cosecha observada en DEV + VAL (6.11): insumo del stress de 6.12
TARGET_MARGIN = 0.05          # margen objetivo sobre saldo promedio para el pricing por riesgo
RATE_FLOOR, RATE_CAP = 0.18, 0.60   # límites de tasa del producto

# --- Motor de decisión (umbrales elegidos en 6.9 con la curva de trade-off) ---
PD_APPROVE_MAX = 0.18         # PD calibrada: hasta aquí, aprobación automática (elegido en 6.9)
PD_REJECT_MIN = 0.20          # PD calibrada: desde aquí, rechazo (elegido en 6.9)
REVIEW_CAPACITY = 0.20        # share máximo de solicitudes que los analistas pueden revisar
MANUAL_REVIEW_AMOUNT = 10_000 # monto desde el cual se verifica el ingreso en efectivo alto
MIN_VIABLE_AMOUNT = 1_000     # monto mínimo comercial: por debajo, la contraoferta no tiene sentido
REVIEW_APPROVAL_RATE = 0.60   # supuesto: proporción de revisiones que el analista termina aprobando


def slug(texto: str) -> str:
    """Nombre de archivo portable: sin tildes, sin espacios y en minúsculas.

    Windows y Linux no codifican igual los acentos en nombres de archivo, así que un
    `modelos_tuning_regresión.csv` generado en Linux se corrompe al abrirlo en Windows.
    Todo archivo que el código genere pasa por aquí.
    """
    limpio = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^A-Za-z0-9]+", "_", limpio).strip("_").lower()
    return limpio
