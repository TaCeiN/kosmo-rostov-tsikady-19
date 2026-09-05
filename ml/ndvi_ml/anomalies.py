"""Задача 2: детекция и интерпретация аномальных периодов вегетации.

Работает по ВОССТАНОВЛЕННОМУ ряду: сначала задача 1 закрывает пропуски,
затем считается z-score относительно климатнормы и ищутся связные периоды
угнетения. Каждому периоду приписывается погодная версия причины.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .baselines import whittaker_weighted

# пороги из постановки задачи
Z_MODERATE = -1.0
Z_CRITICAL = -2.0
MIN_RUN_DAYS = 10          # короче — шум/облако, а не угнетение
DROUGHT_PRECIP_RATIO = 0.6  # осадков меньше 60% нормы за 30 дней -> засушливый фон
HEAT_ANOM_C = 2.0           # температура выше нормы на 2 градуса


def classify_z(z: float) -> str:
    if pd.isna(z):
        return "нет данных"
    if z >= Z_MODERATE:
        return "Штатное развитие"
    if z >= Z_CRITICAL:
        return "Угнетение биомассы"
    return "Критическая аномалия"


def add_zscore(series: pd.DataFrame, value_col: str = "ndvi_filled",
               mean_col: str = "clim_mean", std_col: str = "clim_std") -> pd.DataFrame:
    out = series.copy()
    std = out[std_col].replace(0, np.nan)
    out["z"] = (out[value_col] - out[mean_col]) / std
    out["status_pred"] = out["z"].map(classify_z)
    return out


def VALUE_COL(frame: pd.DataFrame) -> str:
    """Сглаженный ряд, если он построен, иначе сырое заполнение."""
    return "ndvi_smooth" if "ndvi_smooth" in frame else "ndvi_filled"


def find_periods(df: pd.DataFrame, min_days: int = MIN_RUN_DAYS) -> pd.DataFrame:
    """Связные периоды, где z устойчиво ниже -1, по каждому полигону и сезону."""
    rows = []
    for (poly, year), part in df.groupby(["anon_polygon_id", "year"], observed=True):
        part = part.sort_values("date")
        flag = (part["z"] < Z_MODERATE).fillna(False).to_numpy()
        if not flag.any():
            continue
        # разбиваем на серии подряд идущих True
        edges = np.flatnonzero(np.diff(np.r_[0, flag.astype(int), 0]))
        for s, e in zip(edges[::2], edges[1::2]):
            seg = part.iloc[s:e]
            days = (seg["date"].max() - seg["date"].min()).days + 1
            if days < min_days:
                continue
            zmin = float(seg["z"].min())
            rows.append({
                "anon_polygon_id": poly,
                "year": int(year),
                "start": seg["date"].min().date(),
                "end": seg["date"].max().date(),
                "days": days,
                "z_min": zmin,
                "z_mean": float(seg["z"].mean()),
                "ndvi_mean": float(seg[VALUE_COL(seg)].mean()),
                "clim_mean": float(seg["clim_mean"].mean()),
                "drop_vs_norm": float(seg[VALUE_COL(seg)].mean() - seg["clim_mean"].mean()),
                "severity": classify_z(zmin),
                "crop_type": seg["crop_type"].iloc[0],
                "precip_30d": float(seg["precip_30d"].mean()) if "precip_30d" in seg else np.nan,
                "precip_30d_norm": float(seg["precip_30d_norm"].mean()) if "precip_30d_norm" in seg else np.nan,
                "temp_anom": float(seg["temp_anom"].mean()) if "temp_anom" in seg else np.nan,
            })
    return pd.DataFrame(rows)


def explain(periods: pd.DataFrame) -> pd.DataFrame:
    """Приписывает периоду причину по погодному контексту.

    Это версия, а не диагноз: ERA5 объясняет далеко не всё, поэтому в отчёте
    формулировка остаётся гипотезой с указанием опорных цифр.
    """
    if periods.empty:
        return periods
    p = periods.copy()
    ratio = p["precip_30d"] / p["precip_30d_norm"].replace(0, np.nan)
    dry = ratio < DROUGHT_PRECIP_RATIO
    hot = p["temp_anom"] > HEAT_ANOM_C

    cause = np.where(dry & hot, "засуха: осадки ниже нормы и жара",
             np.where(dry, "дефицит осадков",
              np.where(hot, "температурный стресс",
               np.where(p["days"] <= 20, "краткое отклонение, погодой не объясняется "
                                         "(вероятно агрооперация или ошибка данных)",
                        "устойчивое угнетение без явного погодного сигнала"))))
    p["cause"] = cause
    p["precip_ratio"] = ratio.round(2)
    p["comment"] = [
        f"{r.severity}: NDVI {r.ndvi_mean:.2f} против нормы {r.clim_mean:.2f} "
        f"(z={r.z_min:.1f}) в течение {r.days} дн.; {r.cause}"
        for r in p.itertuples()
    ]
    return p.sort_values(["z_min"]).reset_index(drop=True)


def smooth_filled(series: pd.DataFrame, lam: float = 20.0, w_filled: float = 0.25) -> pd.DataFrame:
    """Сглаживает восстановленный ряд: наблюдения держат кривую, предсказания уступают.

    Модель предсказывает каждый день независимо, поэтому суточный ряд получается
    зубчатым: для графика это шум, а для z-score — ложные однодневные провалы.
    Whittaker с весом 1 на наблюдениях и 0.25 на восстановленных точках убирает
    дребезг, не сдвигая ряд от реальных измерений.
    """
    out = series.copy()
    vals = out["ndvi_filled"].to_numpy(dtype=float).copy()
    obs = out["ndvi_obs"].notna().to_numpy()
    for _, idx in out.groupby(["anon_polygon_id", "year"], observed=True).indices.items():
        w = np.where(obs[idx], 1.0, w_filled)
        vals[idx] = whittaker_weighted(vals[idx], w, lam=lam)
    out["ndvi_smooth"] = np.clip(vals, -1.0, 1.0)
    return out


def build_series(df: pd.DataFrame, filled: np.ndarray, feats: pd.DataFrame,
                 smooth: bool = True) -> pd.DataFrame:
    """Собирает ряд для анализа аномалий: восстановленный NDVI + норма + погода."""
    s = pd.DataFrame({
        "anon_polygon_id": df["anon_polygon_id"].to_numpy(),
        "date": df["date"].to_numpy(),
        "year": df["year"].to_numpy(),
        "doy": df["doy"].to_numpy(),
        "crop_type": df["crop_type"].astype(str).to_numpy(),
        "ndvi_obs": df["primary_ndvi"].to_numpy(),
        "ndvi_filled": filled,
        "clim_mean": feats["clim_poly_mean"].to_numpy(),
        "clim_std": feats["clim_poly_std"].to_numpy(),
        "precip_30d": feats["precip_roll21"].to_numpy(),
        "temp_30d": feats["temp_roll21"].to_numpy(),
    })
    # норма погоды по (полигон, фаза сезона) за все годы
    s["doy_bin"] = s["doy"] // 8
    for col, out_col in (("precip_30d", "precip_30d_norm"), ("temp_30d", "temp_30d_norm")):
        norm = s.groupby(["anon_polygon_id", "doy_bin"], observed=True)[col].transform("mean")
        s[out_col] = norm
    s["temp_anom"] = s["temp_30d"] - s["temp_30d_norm"]

    # климатнорма считается по бинам сезона -> в суточном ряду она ступенчатая
    # и дырявая; для графика и z-score её надо сделать непрерывной
    g = s.groupby(["anon_polygon_id", "year"], observed=True)
    for col in ("clim_mean", "clim_std"):
        s[col] = g[col].transform(lambda x: x.interpolate(limit_direction="both")
                                  .rolling(17, center=True, min_periods=1).mean())

    if smooth:
        s = smooth_filled(s)
        return add_zscore(s, value_col="ndvi_smooth")
    return add_zscore(s)
