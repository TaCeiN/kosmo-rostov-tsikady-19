"""Классические методы восстановления ряда — то, с чем сравнивается ML.

Все методы получают ЗАМАСКИРОВАННЫЙ суточный грид и возвращают предсказание
primary_ndvi для каждой строки.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.signal import savgol_filter
from scipy.sparse.linalg import spsolve


def _season(df: pd.DataFrame) -> pd.Series:
    return df["anon_polygon_id"].astype(str) + "_" + df["year"].astype(str)


def _fallback_chain(out: np.ndarray, feats: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Закрывает NaN по цепочке запасных признаков, в конце — глобальным средним.

    Без этого методы сравнивались бы на разном числе точек, и «плохой» метод
    выглядел бы лучше просто потому, что отказался отвечать на трудных строках.
    """
    for col in cols:
        if col in feats:
            out = np.where(np.isnan(out), feats[col].to_numpy(dtype=float), out)
    med = np.nanmedian(feats["clim_all_mean"].to_numpy(dtype=float)) if "clim_all_mean" in feats else 0.4
    return np.where(np.isnan(out), med if np.isfinite(med) else 0.4, out)


def predict_linear(masked: pd.DataFrame, feats: pd.DataFrame) -> np.ndarray:
    """Линейная интерполяция между ближайшими наблюдениями (baseline из постановки)."""
    out = feats["lin_interp"].to_numpy(dtype=float).copy()
    return _fallback_chain(out, feats, ["neighbor_mean", "clim_poly_mean",
                                        "clim_crop_mean", "clim_all_mean"])


def predict_climatology(masked: pd.DataFrame, feats: pd.DataFrame) -> np.ndarray:
    """Только климатическая норма по (полигон, фаза сезона), leave-one-year-out."""
    out = feats["clim_poly_mean"].to_numpy(dtype=float).copy()
    return _fallback_chain(out, feats, ["clim_crop_mean", "clim_all_mean", "lin_interp"])


def predict_clim_anomaly(masked: pd.DataFrame, feats: pd.DataFrame) -> np.ndarray:
    """Норма + перенос аномалии соседних дат (anomaly-preserving интерполяция)."""
    out = feats["clim_plus_anom"].to_numpy(dtype=float).copy()
    return np.where(np.isnan(out), predict_linear(masked, feats), out)


def predict_savgol(masked: pd.DataFrame, feats: pd.DataFrame,
                   window: int = 31, polyorder: int = 2) -> np.ndarray:
    """Savitzky-Golay поверх линейно заполненного ряда."""
    base = predict_linear(masked, feats)
    df = masked.reset_index(drop=True)
    filled = pd.Series(np.where(df["primary_ndvi"].notna(), df["primary_ndvi"], base))
    out = np.full(len(df), np.nan)
    for _, idx in df.groupby(_season(df), observed=True).indices.items():
        y = filled.iloc[idx].to_numpy(dtype=float)
        if np.isnan(y).all():
            continue
        y = pd.Series(y).interpolate(limit_direction="both").to_numpy()
        w = min(window if window % 2 else window + 1, len(y) - (1 - len(y) % 2))
        if w <= polyorder + 1:
            out[idx] = y
            continue
        out[idx] = savgol_filter(y, w, polyorder)
    return np.where(np.isnan(out), base, out)


def whittaker_weighted(y: np.ndarray, w: np.ndarray, lam: float = 50.0) -> np.ndarray:
    """Whittaker с произвольными весами: (W + lam*D'D) z = W y.

    Вес задаёт доверие к точке: 1 для наблюдения, меньше — для восстановленного значения.
    """
    n = len(y)
    if n < 5 or not np.any(w > 0):
        return y.astype(float)
    D = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n), format="csc")
    A = sparse.diags(w, format="csc") + lam * (D.T @ D)
    try:
        return spsolve(A.tocsc(), w * np.nan_to_num(y))
    except Exception:
        return y.astype(float)


def predict_whittaker(masked: pd.DataFrame, feats: pd.DataFrame, lam: float = 50.0) -> np.ndarray:
    """Whittaker smoother: веса 0 в пропусках, штраф на вторую разность.

    Решает (W + lam*D'D) z = W y — заполнение и сглаживание одним шагом.
    """
    base = predict_linear(masked, feats)
    df = masked.reset_index(drop=True)
    y_all = df["primary_ndvi"].to_numpy(dtype=float)
    out = np.full(len(df), np.nan)

    for _, idx in df.groupby(_season(df), observed=True).indices.items():
        y = y_all[idx]
        obs = ~np.isnan(y)
        n = len(y)
        if obs.sum() < 3 or n < 5:
            continue
        w = obs.astype(float)
        yy = np.where(obs, y, 0.0)
        D = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n), format="csc")
        A = sparse.diags(w, format="csc") + lam * (D.T @ D)
        try:
            out[idx] = spsolve(A.tocsc(), w * yy)
        except Exception:
            continue
    return np.where(np.isnan(out), base, out)


BASELINES = {
    "linear": predict_linear,
    "climatology": predict_climatology,
    "clim+anomaly": predict_clim_anomaly,
    "savgol": predict_savgol,
    "whittaker": predict_whittaker,
}
