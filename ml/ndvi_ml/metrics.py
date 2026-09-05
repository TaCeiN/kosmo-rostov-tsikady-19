"""Метрики и диагностика по срезам."""

from __future__ import annotations

import numpy as np
import pandas as pd


def core_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    ok = ~(np.isnan(y) | np.isnan(p))
    y, p = y[ok], p[ok]
    if len(y) == 0:
        return {"n": 0}
    err = p - y
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    denom = np.maximum(np.abs(y), 0.05)  # NDVI около нуля -> MAPE без защиты взрывается
    return {
        "n": int(len(y)),
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "MAE": float(np.mean(np.abs(err))),
        "MedAE": float(np.median(np.abs(err))),
        "R2": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
        "bias": float(np.mean(err)),
        "sMAPE_%": float(np.mean(np.abs(err) / denom) * 100),
        "p90_AE": float(np.quantile(np.abs(err), 0.90)),
        "max_AE": float(np.max(np.abs(err))),
        "within_0.05": float(np.mean(np.abs(err) <= 0.05) * 100),
        "within_0.10": float(np.mean(np.abs(err) <= 0.10) * 100),
    }


def gap_bucket(gap_len: pd.Series) -> pd.Series:
    return pd.cut(gap_len, [0, 3, 7, 16, 31, 10_000],
                  labels=["1-3д", "4-7д", "8-16д", "17-31д", ">31д"])


def phase_bucket(doy: pd.Series) -> pd.Series:
    return pd.cut(doy, [0, 120, 152, 181, 212, 243, 400],
                  labels=["апр", "май", "июн", "июл", "авг", "сен-окт"])


def sliced_report(frame: pd.DataFrame, by: str) -> pd.DataFrame:
    """RMSE/MAE/R2 в разрезе одной колонки."""
    rows = []
    for key, part in frame.groupby(by, observed=True):
        m = core_metrics(part["y"], part["pred"])
        if m["n"] == 0:
            continue
        m[by] = key
        rows.append(m)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).set_index(by)
    return out[["n", "RMSE", "MAE", "R2", "bias", "within_0.05"]].sort_values("RMSE", ascending=False)


def worst_cases(frame: pd.DataFrame, k: int = 15) -> pd.DataFrame:
    f = frame.copy()
    f["abs_err"] = (f["pred"] - f["y"]).abs()
    cols = [c for c in ["anon_polygon_id", "date", "crop_type", "y", "pred", "abs_err",
                        "gap_len", "doy", "year", "scenario"] if c in f.columns]
    return f.nlargest(k, "abs_err")[cols]
