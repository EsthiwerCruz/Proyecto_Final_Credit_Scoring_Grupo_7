"""Expected Loss, cartera y stress testing (sección 6.12).

Integra las tres piezas: **PD calibrada** (6.7), **factor de exposición** (6.10) y **LGD**
(6.11), a nivel de cada solicitud y de cartera.

    EL_i = PD_i x (EAD_i / monto_i) x LGD_i x monto_i

Dos decisiones que se toman aquí y se documentan en el reporte:

* **Base de la LGD.** La LGD del archivo no descuenta. Se adopta la **LGD económica**,
  descontada a la tasa efectiva de los créditos que la política realmente colocaría, y se
  **restatea en la misma base el umbral de pérdida esperada del apetito**: cambiar la
  métrica sin cambiar el umbral rompería el semáforo por definición y no por riesgo.
* **Capital de riesgo.** Se aproxima con la fórmula IRB de Basilea para *other retail*,
  que da la pérdida inesperada al 99.9% y permite comparar escenarios en la misma unidad.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from . import config as cfg


# ---------------------------------------------------------------------------
# Expected Loss
# ---------------------------------------------------------------------------
def expected_loss_frame(df: pd.DataFrame, pd_hat, monto=None, ead_factor: float = cfg.EAD_FACTOR_BASELINE,
                        lgd: float = cfg.LGD_BASELINE) -> pd.DataFrame:
    """Componentes de la pérdida esperada por solicitud (nivel cliente)."""
    monto = df["requested_amount"].to_numpy(dtype=float) if monto is None else np.asarray(monto, dtype=float)
    pd_hat = np.asarray(pd_hat, dtype=float)
    ead = ead_factor * monto
    return pd.DataFrame({"monto": monto, "pd": pd_hat, "ead_factor": ead_factor, "ead": ead,
                         "lgd": lgd, "el": pd_hat * ead * lgd}, index=df.index)


def portfolio_summary(el: pd.DataFrame) -> dict:
    """Agregados de cartera: exposición, PD y LGD ponderadas, EL y tasa de EL sobre monto."""
    monto = el["monto"].sum()
    return {"creditos": int(len(el)), "monto": float(monto), "ead": float(el["ead"].sum()),
            "pd_ponderada": float((el["pd"] * el["monto"]).sum() / monto),
            "lgd_ponderada": float((el["lgd"] * el["monto"]).sum() / monto),
            "el": float(el["el"].sum()), "el_sobre_monto": float(el["el"].sum() / monto)}


def hhi(shares) -> float:
    """Índice de Herfindahl-Hirschman de concentración (0 = atomizada, 1 = un solo segmento)."""
    s = np.asarray(shares, dtype=float)
    return float(np.sum((s / s.sum()) ** 2))


def segment_dashboard(df: pd.DataFrame, el: pd.DataFrame, segmentos: dict, y_obs=None) -> pd.DataFrame:
    """Tablero por segmento: exposición, PD, LGD, EL, concentración y default observado."""
    filas = []
    for nombre, serie in segmentos.items():
        g = pd.DataFrame({"seg": serie.astype(str).to_numpy()}, index=df.index).join(el)
        if y_obs is not None:
            g["y"] = np.asarray(y_obs, dtype=float)
        t = g.groupby("seg").apply(lambda x: pd.Series({
            "creditos": len(x), "monto": x["monto"].sum(), "pct_monto": x["monto"].sum() / el["monto"].sum(),
            "pd_ponderada": (x["pd"] * x["monto"]).sum() / x["monto"].sum(),
            "ead": x["ead"].sum(), "lgd": x["lgd"].mean(), "el": x["el"].sum(),
            "el_sobre_monto": x["el"].sum() / x["monto"].sum(),
            "pct_el": x["el"].sum() / el["el"].sum(),
            "default_observado": x["y"].mean() if "y" in x else np.nan}))
        t.insert(0, "dimension", nombre)
        filas.append(t.sort_values("pct_el", ascending=False))
    return pd.concat(filas)


# ---------------------------------------------------------------------------
# Capital de riesgo (IRB de Basilea, cartera minorista "other retail")
# ---------------------------------------------------------------------------
def basel_capital(pd_hat, lgd, ead, confianza: float = 0.999) -> dict:
    """Pérdida inesperada al 99.9% con la fórmula IRB de *other retail*.

    R = 0.03 (1−e^(−35 PD)) / (1−e^(−35)) + 0.16 [1 − (1−e^(−35 PD))/(1−e^(−35))]
    K = LGD [ N( (N⁻¹(PD) + √R N⁻¹(0.999)) / √(1−R) ) − PD ]

    No pretende ser el capital regulatorio del producto: es una vara común para comparar
    escenarios en unidades de capital, no solo de pérdida esperada.
    """
    p = np.clip(np.asarray(pd_hat, dtype=float), 1e-6, 1 - 1e-6)
    lgd = np.asarray(lgd, dtype=float)
    ead = np.asarray(ead, dtype=float)
    base = (1 - np.exp(-35 * p)) / (1 - np.exp(-35.0))
    r = 0.03 * base + 0.16 * (1 - base)
    cond = stats.norm.cdf((stats.norm.ppf(p) + np.sqrt(r) * stats.norm.ppf(confianza)) / np.sqrt(1 - r))
    k = lgd * (cond - p)
    return {"capital": float(np.sum(k * ead)), "capital_sobre_ead": float(np.sum(k * ead) / np.sum(ead)),
            "rwa": float(np.sum(k * ead) * 12.5)}


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------
@dataclass
class Escenario:
    """Shock multiplicativo sobre las odds de default y niveles de LGD y exposición.

    El shock de PD se aplica sobre las **odds** y no sobre la PD, para que no se salga de
    [0, 1] y para que el deterioro sea proporcional en toda la distribución, que es como se
    observó entre 2021 y 2024 (6.4: desplazamiento de nivel con pendiente estable).
    """
    nombre: str
    odds_pd: float = 1.0
    lgd: float = cfg.LGD_BASELINE
    ead_factor: float = cfg.EAD_FACTOR_BASELINE
    justificacion: str = ""
    meta: dict = field(default_factory=dict)

    def pd_shock(self, pd_hat) -> np.ndarray:
        p = np.clip(np.asarray(pd_hat, dtype=float), 1e-6, 1 - 1e-6)
        odds = p / (1 - p) * self.odds_pd
        return odds / (1 + odds)


def run_scenarios(df: pd.DataFrame, pd_base, escenarios: list[Escenario], politica, recalcular_pd=None,
                  default_observado=None) -> pd.DataFrame:
    """Aplica cada escenario y devuelve cartera, riesgo, economía y capital.

    Importante: la política se **vuelve a aplicar** con la PD shockeada. Los umbrales están
    en la escala de PD calibrada, así que un deterioro reduce la aprobación de forma
    automática: la cartera resultante no es la misma cartera con más pérdida.
    """
    from . import decision as dec

    filas = []
    for e in escenarios:
        p = e.pd_shock(pd_base)
        d = politica.decide(df, p, recalcular_pd=None if recalcular_pd is None else (lambda x, e=e: e.pd_shock(recalcular_pd(x))))
        aprobados = d["decision"].eq(dec.APPROVE).to_numpy()
        revisados = d["decision"].eq(dec.REVIEW).to_numpy()
        peso = np.where(aprobados, 1.0, np.where(revisados, cfg.REVIEW_APPROVAL_RATE, 0.0))
        monto = d["monto_recomendado"].fillna(0).to_numpy() * peso
        el = expected_loss_frame(df, p, monto=monto, ead_factor=e.ead_factor, lgd=e.lgd)
        margen = dec.expected_margin(df, d["tasa_recomendada"].fillna(0).to_numpy(), monto)
        cap = basel_capital(p[peso > 0], e.lgd, el.loc[peso > 0, "ead"])
        y = None if default_observado is None else np.asarray(default_observado, dtype=float)
        filas.append({
            "escenario": e.nombre, "odds_pd": e.odds_pd, "lgd": e.lgd, "ead_factor": e.ead_factor,
            "aprobacion_final": float(peso.mean()), "monto_colocado": float(monto.sum()),
            "pd_ponderada": float((p * monto).sum() / monto.sum()),
            "default_esperado": float((p * peso).sum() / peso.sum()),
            "el": float(el["el"].sum()), "el_sobre_monto": float(el["el"].sum() / monto.sum()),
            "margen_sobre_monto": float(margen.sum() / monto.sum()),
            "resultado_sobre_monto": float((margen.sum() - el["el"].sum()) / monto.sum()),
            "capital_sobre_ead": cap["capital_sobre_ead"], "capital": cap["capital"],
            "justificacion": e.justificacion})
    return pd.DataFrame(filas).set_index("escenario")


# ---------------------------------------------------------------------------
# Tablero reproducible
# ---------------------------------------------------------------------------
def build_dashboard(ruta, titulo: str, resumen: dict, tablas: dict, figuras: list, notas: str = "") -> str:
    """Genera un tablero HTML autocontenido (tablas + figuras embebidas en base64)."""
    def tarjeta(k, v):
        return f'<div class="kpi"><div class="kpi-v">{v}</div><div class="kpi-k">{k}</div></div>'

    kpis = "".join(tarjeta(k, v) for k, v in resumen.items())
    bloques = []
    for nombre, t in tablas.items():
        bloques.append(f"<h2>{nombre}</h2>" + t.to_html(classes="tabla", border=0, float_format=lambda x: f"{x:,.4f}"))
    imgs = []
    for f in figuras:
        b64 = base64.b64encode(open(f, "rb").read()).decode()
        imgs.append(f'<img src="data:image/png;base64,{b64}" />')
    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title><style>
:root {{ --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --line:#e1e0d9; --bg:#fcfcfb; --blue:#2a78d6; }}
* {{ box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:var(--ink);
background:var(--bg); margin:0; padding:24px; line-height:1.5; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:28px 0 8px; color:var(--ink2); }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:18px; }}
.kpis {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:8px; }}
.kpi {{ border:1px solid var(--line); border-radius:10px; padding:10px 14px; min-width:150px; background:#fff; }}
.kpi-v {{ font-size:19px; font-weight:600; }} .kpi-k {{ font-size:11.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; }}
table.tabla {{ border-collapse:collapse; width:100%; font-size:12.5px; background:#fff; }}
table.tabla th, table.tabla td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:right; }}
table.tabla th {{ text-align:left; color:var(--ink2); font-weight:600; }}
table.tabla td:first-child, table.tabla th:first-child {{ text-align:left; }}
.scroll {{ overflow-x:auto; }} img {{ max-width:100%; margin:10px 0; border:1px solid var(--line); border-radius:8px; background:#fff; }}
.nota {{ font-size:12.5px; color:var(--ink2); border-left:3px solid var(--blue); padding:8px 12px; margin-top:20px; background:#fff; }}
</style></head><body>
<h1>{titulo}</h1><div class="sub">Generado por <code>notebooks/09_expected_loss_stress.ipynb</code> · se regenera con cada corrida</div>
<div class="kpis">{kpis}</div>
<div class="scroll">{''.join(bloques)}</div>
{''.join(imgs)}
{f'<div class="nota">{notas}</div>' if notas else ''}
</body></html>"""
    ruta = str(ruta)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta
