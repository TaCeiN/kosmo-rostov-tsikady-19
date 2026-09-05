"""Ядро ночной лаборатории: гоняет конфигурации по кэшу фолдов и копит результаты.

Одна конфигурация = словарь. Что можно крутить:
  params        — параметры LightGBM (мержатся поверх дефолтных)
  n_estimators  — число деревьев
  target        — 'raw' | 'resid_whittaker' | 'resid_savgol' | 'resid_lin'
                  (учить не сам NDVI, а поправку к сглаживателю)
  drop_broken   — выкинуть из ОБУЧЕНИЯ строки с физически невозможным NDVI
  weight        — None | 'gap' | 'inv_gap' — веса примеров по длине пропуска
  split_gap     — обучать отдельную модель для дырок длиннее порога
  clip          — обрезка предсказаний по физике NDVI

Результаты дописываются в night/results.csv после КАЖДОЙ конфигурации,
предсказания складываются в night/preds/ — чтобы потом собирать ансамбли
без переобучения и чтобы ничего не потерялось, если контейнер умрёт.
"""
from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / os.environ.get("NDVI_CACHE", "cache")
NIGHT = ROOT / "night"
RESULTS = NIGHT / os.environ.get("NDVI_RESULTS", "results.csv")
PREDS = NIGHT / "preds"

BASE_PARAMS = dict(objective="regression", metric="rmse", learning_rate=0.04,
                   num_leaves=63, min_data_in_leaf=40, feature_fraction=0.75,
                   bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
                   num_threads=0, verbosity=-1, seed=0)

_FOLDS: dict[str, dict] | None = None


def load_folds(names: list[str] | None = None) -> dict[str, dict]:
    """Читает кэш фолдов с диска (один раз за процесс)."""
    global _FOLDS
    if _FOLDS is None:
        _FOLDS = {}
        for p in sorted(CACHE.glob("new_polygon_fold*.pkl")):
            with open(p, "rb") as f:
                _FOLDS[p.stem] = pickle.load(f)
    return {k: v for k, v in _FOLDS.items() if names is None or k in names}


def _drop(X: pd.DataFrame, patterns: list[str] | None) -> pd.DataFrame:
    """Убирает признаки по префиксам — для абляции без пересборки кэша."""
    if not patterns:
        return X
    cols = [c for c in X.columns if not any(c.startswith(p) for p in patterns)]
    return X[cols]


def _prep(X: pd.DataFrame) -> pd.DataFrame:
    X = X.copy()
    if "crop_type" in X:
        X["crop_type"] = X["crop_type"].astype("category")
    return X


def _anchor(X: pd.DataFrame, target: str) -> np.ndarray:
    """Опорное значение, к которому модель учит поправку."""
    col = {"resid_whittaker": "sm_whittaker", "resid_savgol": "sm_savgol",
           "resid_lin": "lin_interp"}[target]
    a = X[col].to_numpy(dtype=float)
    if np.isnan(a).any():  # lin_interp местами пуст
        fb = X["sm_whittaker"].to_numpy(dtype=float)
        a = np.where(np.isnan(a), fb, a)
    return a


def _weights(X: pd.DataFrame, mode: str | None) -> np.ndarray | None:
    if not mode:
        return None
    g = X["gap_len"].to_numpy(dtype=float)
    g = np.nan_to_num(g, nan=np.nanmedian(g))
    if mode == "gap":         # длинные дырки важнее — их труднее и они дороже
        return np.clip(g / 10.0, 0.5, 4.0)
    if mode == "inv_gap":     # наоборот, доверять коротким
        return np.clip(10.0 / np.maximum(g, 1), 0.5, 4.0)
    raise ValueError(mode)


def _train_one(X: pd.DataFrame, y: np.ndarray, cfg: dict, seed: int):
    params = {**BASE_PARAMS, **cfg.get("params", {}), "seed": seed}
    ds = lgb.Dataset(_prep(X), label=y, weight=_weights(X, cfg.get("weight")))
    return lgb.train(params, ds, num_boost_round=cfg.get("n_estimators", 1200))


def run_config(cfg: dict, folds: dict[str, dict] | None = None,
               seeds: tuple[int, ...] = (0,)) -> dict:
    """Обучает и меряет конфигурацию на всех фолдах. Возвращает строку метрик."""
    folds = folds or load_folds()
    t0 = time.time()
    target = cfg.get("target", "raw")
    all_y, all_p, per_fold, fold_preds = [], [], {}, {}

    for name, d in folds.items():
        drop = cfg.get("drop_features")
        X_tr, y_tr = _drop(d["X_tr"], drop), d["y_tr"].astype(float)
        X_ev, y_ev = _drop(d["X_ev"], drop), d["y_ev"].astype(float)

        keep = np.ones(len(y_tr), dtype=bool)
        if cfg.get("drop_broken", False):
            keep &= (y_tr >= -1) & (y_tr <= 1)
        Xt, yt = X_tr[keep], y_tr[keep]

        if target == "raw":
            fit_y, anchor_tr, anchor_ev = yt, 0.0, 0.0
        else:
            anchor_tr = _anchor(Xt, target)
            anchor_ev = _anchor(X_ev, target)
            fit_y = yt - anchor_tr

        if cfg.get("split_gap"):
            thr = float(cfg["split_gap"])
            gt = np.nan_to_num(Xt["gap_len"].to_numpy(dtype=float), nan=0)
            ge = np.nan_to_num(X_ev["gap_len"].to_numpy(dtype=float), nan=0)
            pred = np.zeros(len(X_ev))
            for mask_tr, mask_ev in ((gt <= thr, ge <= thr), (gt > thr, ge > thr)):
                if mask_ev.sum() == 0:
                    continue
                if mask_tr.sum() < 500:      # мало данных — учим на всём
                    mask_tr = np.ones(len(Xt), dtype=bool)
                ps = [_train_one(Xt[mask_tr], fit_y[mask_tr], cfg, s).predict(
                      _prep(X_ev[mask_ev])) for s in seeds]
                pred[mask_ev] = np.mean(ps, axis=0)
        else:
            ps = [_train_one(Xt, fit_y, cfg, s).predict(_prep(X_ev)) for s in seeds]
            pred = np.mean(ps, axis=0)

        pred = pred + anchor_ev
        lo, hi = cfg.get("clip", (-0.2, 1.0))
        pred = np.clip(pred, lo, hi)

        per_fold[name] = float(np.sqrt(np.mean((pred - y_ev) ** 2)))
        fold_preds[name] = pred
        all_y.append(y_ev); all_p.append(pred)

    y = np.concatenate(all_y); p = np.concatenate(all_p)
    err = p - y
    ok = (y >= -1) & (y <= 1)
    row = {
        "name": cfg["name"],
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "RMSE_clean": float(np.sqrt(np.mean(err[ok] ** 2))),
        "MAE": float(np.mean(np.abs(err))),
        "MedAE": float(np.median(np.abs(err))),
        "within_0.05": float(np.mean(np.abs(err) <= 0.05) * 100),
        "bias": float(np.mean(err)),
        "n": int(len(y)),
        "secs": round(time.time() - t0, 1),
        "cfg": json.dumps({k: v for k, v in cfg.items() if k != "name"}, ensure_ascii=False),
    }
    row.update({f"f{i}": v for i, (k, v) in enumerate(sorted(per_fold.items()))})

    PREDS.mkdir(parents=True, exist_ok=True)
    np.savez(PREDS / f"{cfg['name']}.npz", **fold_preds)
    return row


def append_result(row: dict) -> None:
    """Дописывает строку результата сразу на диск."""
    df = pd.DataFrame([row])
    df.to_csv(RESULTS, mode="a", header=not RESULTS.exists(), index=False)


def leaderboard(top: int = 25) -> pd.DataFrame:
    if not RESULTS.exists():
        return pd.DataFrame()
    d = pd.read_csv(RESULTS).drop_duplicates("name", keep="last")
    return d.sort_values("RMSE").head(top)


def wins_vs(name: str, baseline: str = "baseline") -> str:
    """На скольких фолдах конфигурация побила базовую — защита от шума."""
    d = pd.read_csv(RESULTS).drop_duplicates("name", keep="last").set_index("name")
    cols = [c for c in d.columns if c.startswith("f") and c[1:].isdigit()]
    if name not in d.index or baseline not in d.index:
        return "?"
    w = int((d.loc[name, cols].to_numpy() < d.loc[baseline, cols].to_numpy()).sum())
    return f"{w}/{len(cols)}"
