"""LightGBM-модель восстановления primary_ndvi."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None

from sklearn.ensemble import HistGradientBoostingRegressor

PARAMS = dict(
    objective="regression",
    metric="rmse",
    learning_rate=0.02,   # подобрано ночным перебором: медленнее и глубже лучше
    num_leaves=63,
    min_data_in_leaf=25,   # было 40: меньший лист точнее улавливает 15-дневный весенний пик пшеницы
    feature_fraction=0.75,
    bagging_fraction=0.8,
    bagging_freq=1,
    lambda_l2=1.0,
    num_threads=0,
    verbosity=-1,
)


def _prep(X: pd.DataFrame) -> pd.DataFrame:
    X = X.copy()
    if "crop_type" in X:
        X["crop_type"] = X["crop_type"].astype("category")
    return X


class NdviModel:
    """Обёртка: LightGBM, если стоит, иначе sklearn HistGB."""

    def __init__(self, n_estimators: int = 2500, params: dict | None = None, seed: int = 0):
        self.n_estimators = n_estimators
        self.params = {**PARAMS, **(params or {}), "seed": seed}
        self.model = None
        self.feature_names: list[str] = []

    def fit(self, X: pd.DataFrame, y: np.ndarray,
            X_val: pd.DataFrame | None = None, y_val: np.ndarray | None = None):
        X = _prep(X)
        self.feature_names = list(X.columns)
        if lgb is not None:
            w = np.ones(len(X), dtype=float)
            if "crop_type" in X.columns:
                # Фокус на озимой пшенице (основная культура теста, дающая наибольшую ошибку)
                w *= np.where(X["crop_type"].astype(str) == "озимая пшеница", 1.4, 1.0)
            if "doy" in X.columns:
                # Фокус на фазе весеннего отрастания (DOY 90-160), где сосредоточена основная ошибка
                w *= np.where((X["doy"] >= 90) & (X["doy"] <= 160), 1.25, 1.0)
            ds = lgb.Dataset(X, label=y, weight=w)
            valid, names, cbs = [ds], ["train"], []
            if X_val is not None and len(X_val):
                valid.append(lgb.Dataset(_prep(X_val)[self.feature_names], label=y_val))
                names.append("valid")
                cbs.append(lgb.early_stopping(80, verbose=False))
            self.model = lgb.train(self.params, ds, num_boost_round=self.n_estimators,
                                   valid_sets=valid, valid_names=names, callbacks=cbs)
        else:
            X = X.assign(crop_type=X["crop_type"].cat.codes) if "crop_type" in X else X
            self.model = HistGradientBoostingRegressor(
                max_iter=self.n_estimators, learning_rate=self.params["learning_rate"],
                max_leaf_nodes=self.params["num_leaves"], random_state=self.params["seed"])
            self.model.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = _prep(X)[self.feature_names]
        if lgb is not None:
            p = self.model.predict(X, num_iteration=getattr(self.model, "best_iteration", None))
        else:
            X = X.assign(crop_type=X["crop_type"].cat.codes) if "crop_type" in X else X
            p = self.model.predict(X)
        return np.clip(p, -0.02, 0.93)  # границы реальной разметки организаторов

    def importance(self) -> pd.DataFrame:
        if lgb is None or self.model is None:
            return pd.DataFrame()
        return (pd.DataFrame({
            "feature": self.model.feature_name(),
            "gain": self.model.feature_importance("gain"),
            "split": self.model.feature_importance("split"),
        }).sort_values("gain", ascending=False).reset_index(drop=True))
