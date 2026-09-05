"""Обученная модель как единый объект: сохранить, загрузить, применить.

Это то, что встраивается в веб-сервис. Внутри — обученный LightGBM плюс вся
конфигурация препроцессинга, чтобы инференс не зависел от параметров,
которые подбирались при обучении.

    pipe = NdviPipeline.load("model/ndvi_model.pkl")
    result = pipe.predict_frame(df)   # df в схеме исходных данных
    result.series      # суточный ряд: наблюдения, восстановленное, норма, z
    result.anomalies   # периоды угнетения с интерпретацией
    result.filled      # np.ndarray восстановленного NDVI по строкам df
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .anomalies import build_series, explain, find_periods
from .data import MASKED_COLS, mask_rows
from .experiment import build_all_features


@dataclass
class InferenceResult:
    filled: np.ndarray          # восстановленный NDVI для каждой строки входа
    series: pd.DataFrame        # ряд с нормой, z-score и статусом
    anomalies: pd.DataFrame     # найденные периоды


class NdviPipeline:
    """Модель + конфигурация препроцессинга в одном объекте."""

    VERSION = 1

    def __init__(self, booster, feature_names: list[str], config: dict | None = None,
                 cb_model=None):
        # booster может быть одним Booster или списком нескольких Booster (ансамбль)
        if isinstance(booster, (list, tuple)):
            self.boosters = list(booster)
            self.booster = self.boosters[0]
        else:
            self.booster = booster
            self.boosters = [booster]
        self.feature_names = feature_names
        self.config = config or {}
        self.cb_model = cb_model

    # ---------------------------------------------------------------- ввод/вывод

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        model_strs = [b.model_to_string() for b in self.boosters]
        dump_dict = {
            "version": self.VERSION,
            "model": model_strs[0],
            "models": model_strs,
            "feature_names": self.feature_names,
            "config": self.config,
        }
        if self.cb_model is not None:
            dump_dict["cb_model"] = pickle.dumps(self.cb_model)
        with open(path, "wb") as f:
            pickle.dump(dump_dict, f, protocol=4)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "NdviPipeline":
        import lightgbm as lgb
        with open(path, "rb") as f:
            d = pickle.load(f)
        if d.get("version") != cls.VERSION:
            raise ValueError(f"несовместимая версия модели: {d.get('version')}")
        cb_model = pickle.loads(d["cb_model"]) if "cb_model" in d else None
        if "models" in d:
            boosters = [lgb.Booster(model_str=s) for s in d["models"]]
            return cls(boosters, d["feature_names"], d.get("config", {}), cb_model=cb_model)
        return cls(lgb.Booster(model_str=d["model"]), d["feature_names"], d.get("config", {}), cb_model=cb_model)

    # ---------------------------------------------------------------- применение

    def _raw_predict(self, F: pd.DataFrame) -> np.ndarray:
        X = F[self.feature_names].copy()
        if "crop_type" in X:
            X["crop_type"] = X["crop_type"].astype("category")
        # усредняем предсказания всех моделей в ансамбле
        preds = [b.predict(X) for b in self.boosters]
        p = np.mean(preds, axis=0)
        if self.cb_model is not None:
            cb_pred = self.cb_model.predict(X)
            p = 0.75 * p + 0.25 * cb_pred

        target = self.config.get("target", "raw")
        if target != "raw":
            col = {"resid_whittaker": "sm_whittaker", "resid_savgol": "sm_savgol",
                   "resid_lin": "lin_interp"}[target]
            anchor = F[col].to_numpy(dtype=float)
            if np.isnan(anchor).any():
                anchor = np.where(np.isnan(anchor), F["sm_whittaker"].to_numpy(dtype=float), anchor)
            p = p + anchor

        # short-gap blend если настроен
        short_w = self.config.get("short_gap_blend", 0.0)
        if short_w > 0 and "gap_len" in F.columns and "lin_interp" in F.columns:
            short_mask = (F["gap_len"] <= 2) & F["lin_interp"].notna()
            p = np.where(short_mask, (1 - short_w) * p + short_w * F["lin_interp"].to_numpy(), p)

        lo, hi = self.config.get("clip", (-0.02, 0.93))
        return np.clip(p, lo, hi)

    def predict_frame(self, df: pd.DataFrame, with_anomalies: bool = True) -> InferenceResult:
        """Полный проход по кадру в схеме исходных данных.

        Строки без primary_ndvi восстанавливаются, наблюдения остаются как есть.

        Что подавать на вход:
        * суточную сетку сезона, а не только даты наблюдений — соседи, скользящие
          окна и погодные накопления считаются именно по ней;
        * ВСЮ доступную историю полигона, а не один сезон. Климатнорма строится
          leave-one-year-out, поэтому на единственном сезоне она пуста, z-score
          не считается и аномалии молча не находятся;
        * по возможности несколько полигонов сразу — пространственные признаки
          смотрят, что творится у соседних полей в ту же дату.
        """
        df = self._normalize(df)
        # маскируем то, чего в целевых строках быть не может, и считаем признаки
        hidden = df["primary_ndvi"].isna().to_numpy()
        F = build_all_features(mask_rows(df, hidden))
        pred = self._raw_predict(F)
        filled = np.where(df["primary_ndvi"].notna(), df["primary_ndvi"], pred)

        if not with_anomalies:
            return InferenceResult(filled, pd.DataFrame(), pd.DataFrame())
        series = build_series(df, filled, F)
        return InferenceResult(filled, series, explain(find_periods(series)))

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Приводит произвольный вход к схеме, которую ждут признаки."""
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"])
        for col in MASKED_COLS:
            if col not in d.columns:
                d[col] = np.nan
            d[col] = pd.to_numeric(d[col], errors="coerce")
        if "crop_type" not in d.columns:
            d["crop_type"] = "неизвестно"
        d["crop_type"] = d["crop_type"].astype("category")
        d["year"] = d["date"].dt.year.astype(np.int32)
        d["doy"] = d["date"].dt.dayofyear.astype(np.int32)
        d["is_target"] = d["primary_ndvi"].isna() if "primary_ndvi" in d else True
        return d.sort_values(["anon_polygon_id", "date"]).reset_index(drop=True)
