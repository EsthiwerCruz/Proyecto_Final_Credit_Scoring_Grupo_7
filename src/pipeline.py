"""Pipeline reproducible de tratamiento de datos (sección 6.3).

Encapsula, en un único objeto de scikit-learn, todo lo que "aprende" del dato:
recálculo del dti y variables derivadas, winsorización, imputación de faltantes
y encoding de categóricas. Se ajusta **solo con DEV** y se aplica igual a VAL,
OOT y a cualquier solicitud nueva, de modo que no haya diferencias entre
desarrollo y producción.

Los indicadores de faltante se calculan en `FeatureBuilder` pero no entran a la
matriz del modelo: los faltantes son compatibles con MCAR (ver 6.3) y los
indicadores se usan en la política y el monitoreo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import data as data_mod
from . import features as feat


class FeatureBuilder(BaseEstimator, TransformerMixin):
    """Recalcula dti y agrega las variables derivadas de 6.3 (sin estadísticos de la muestra)."""

    def __init__(self, annual_rate: float | None = None):
        self.annual_rate = annual_rate

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(pd.DataFrame(X).columns, dtype=object)
        return self

    def transform(self, X):
        kwargs = {} if self.annual_rate is None else {"annual_rate": self.annual_rate}
        return feat.build_features(X, **kwargs)

    def get_feature_names_out(self, input_features=None):
        entrada = list(input_features if input_features is not None else self.feature_names_in_)
        nuevas = ["dti"] + feat.DERIVED_FEATURES
        return np.asarray(entrada + [c for c in nuevas if c not in entrada], dtype=object)


class Winsorizer(BaseEstimator, TransformerMixin):
    """Acota cada variable a los percentiles aprendidos en el ajuste (por defecto 1% y 99%)."""

    def __init__(self, lower_q: float = 0.01, upper_q: float = 0.99):
        self.lower_q = lower_q
        self.upper_q = upper_q

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.lower_ = X.quantile(self.lower_q)
        self.upper_ = X.quantile(self.upper_q)
        return self

    def transform(self, X):
        X = pd.DataFrame(X)
        return X.clip(lower=self.lower_, upper=self.upper_, axis=1)

    def get_feature_names_out(self, input_features=None):
        return np.asarray(input_features if input_features is not None else self.feature_names_in_, dtype=object)


def pipeline_input_columns() -> list[str]:
    """Esquema de entrada: columnas que debe traer una solicitud para ser puntuada.

    Son las candidatas del catálogo de 6.2 excepto `dti`, que el pipeline recalcula
    desde la cuota de deudas y el ingreso (así nunca existe un dti sin ingreso). Fijar
    el esquema evita que el pipeline se ajuste con columnas auxiliares (como la muestra
    temporal) que en producción no existen.
    """
    return [c for c in data_mod.pd_candidate_features() if c != "dti"]


def model_columns() -> tuple[list[str], list[str]]:
    """Columnas que entran a la matriz del modelo: candidatas de 6.2 + derivadas conservadas en 6.3.

    Devuelve (numéricas, categóricas). Las categóricas son las del catálogo de 6.2.
    Los indicadores de faltante y las derivadas descartadas no forman parte de la matriz.
    """
    candidatas = data_mod.pd_candidate_features()
    cat_cols = ["region", "channel", "employment_type"]
    num_cols = [c for c in candidatas if c not in cat_cols] + feat.DERIVED_CANDIDATES
    return num_cols, cat_cols


def build_preprocessor(num_cols: list[str], cat_cols: list[str], scale: bool = True,
                       lower_q: float = 0.01, upper_q: float = 0.99) -> ColumnTransformer:
    """Numéricas: winsorización -> imputación por mediana -> (opcional) estandarización.
    Categóricas: imputación por moda -> one-hot con manejo de categorías no vistas."""
    num_steps = [("winsor", Winsorizer(lower_q, upper_q)), ("imputer", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scaler", StandardScaler()))
    cat_steps = [("imputer", SimpleImputer(strategy="most_frequent")),
                 ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]
    return ColumnTransformer(
        [("num", Pipeline(num_steps), num_cols), ("cat", Pipeline(cat_steps), cat_cols)],
        remainder="drop", verbose_feature_names_out=False,
    )


def build_pipeline(scale: bool = True) -> Pipeline:
    """Pipeline completo: variables derivadas + preprocesamiento."""
    num_cols, cat_cols = model_columns()
    pipe = Pipeline([("features", FeatureBuilder()),
                     ("prep", build_preprocessor(num_cols, cat_cols, scale=scale))])
    return pipe.set_output(transform="pandas")
