"""Признаки для восстановления primary_ndvi.

Главное правило: все признаки считаются по УЖЕ замаскированной копии данных
(см. data.mask_rows). Строка-цель не видит ни своего NDVI, ни своих спутниковых
индексов, ни своей погоды, ни климатнормы — ровно как в private_features.csv.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEASON_KEY = ["anon_polygon_id", "year"]
DOY_BIN = 8  # ширина бина сезона в днях для климатнормы


# ---------------------------------------------------------------- утилиты


def _prev_next(values: pd.Series, groups: pd.Series, daynum: np.ndarray):
    """Ближайшее известное значение до и после строки внутри группы.

    Возвращает (prev_val, next_val, dt_prev, dt_next, prev_pos, next_pos).
    dt в днях, положительные. Позиции — глобальные индексы строк или -1.
    """
    n = len(values)
    idx = np.arange(n, dtype=np.float64)
    pos = pd.Series(np.where(values.notna().to_numpy(), idx, np.nan), index=values.index)

    # shift и ffill строго внутри группы: сосед из прошлого сезона — не сосед
    gp = pos.groupby(groups, observed=True)
    prev_pos = gp.shift(1).groupby(groups, observed=True).ffill()
    next_pos = gp.shift(-1).groupby(groups, observed=True).bfill()

    pv = prev_pos.to_numpy()
    nx = next_pos.to_numpy()
    vals = values.to_numpy(dtype=np.float64)

    def take(p):
        ok = ~np.isnan(p)
        out = np.full(n, np.nan)
        out[ok] = vals[p[ok].astype(np.int64)]
        return out

    def dt(p):
        ok = ~np.isnan(p)
        out = np.full(n, np.nan)
        out[ok] = np.abs(daynum[ok] - daynum[p[ok].astype(np.int64)])
        return out

    prev_i = np.where(np.isnan(pv), -1, np.nan_to_num(pv, nan=-1)).astype(np.int64)
    next_i = np.where(np.isnan(nx), -1, np.nan_to_num(nx, nan=-1)).astype(np.int64)
    return take(pv), take(nx), dt(pv), dt(nx), prev_i, next_i


def _nanmean2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Среднее двух массивов, игнорируя NaN, без предупреждений на пустых срезах."""
    s = np.nansum(np.vstack([a, b]), axis=0)
    c = (~np.isnan(a)).astype(float) + (~np.isnan(b)).astype(float)
    return np.where(c > 0, s / np.where(c == 0, 1, c), np.nan)


def _loo_stat(values: pd.Series, groups: pd.Series, stat: str) -> np.ndarray:
    """Статистика по группе БЕЗ учёта самой строки.

    Иначе у видимых строк признак подсматривает собственный NDVI, а у скрытых нет,
    и обучение расходится с инференсом.
    """
    g = values.groupby(groups, observed=True)
    s = g.transform("sum")
    c = g.transform("count")
    self_v = values.fillna(0.0)
    self_c = values.notna().astype(float)
    n = c - self_c
    mean = (s - self_v) / n.replace(0, np.nan)
    if stat == "mean":
        return mean.to_numpy()
    if stat == "count":
        return n.to_numpy()
    if stat == "std":
        sq = (values ** 2).groupby(groups, observed=True).transform("sum") - self_v ** 2
        var = sq / n.replace(0, np.nan) - mean ** 2
        return np.sqrt(var.clip(lower=0)).to_numpy()
    raise ValueError(stat)


def _roll(values: pd.Series, groups: pd.Series, window: int, stat: str = "mean") -> np.ndarray:
    """Центрированное окно ±window дней, исключая саму строку.

    Сетка суточная и непрерывная внутри сезона, поэтому окно по строкам == окно по дням.
    """
    g = values.groupby(groups, observed=True)
    r = g.rolling(2 * window + 1, center=True, min_periods=1)
    s = r.sum().reset_index(level=0, drop=True)
    c = r.count().reset_index(level=0, drop=True)
    self_v = values.fillna(0.0)
    self_c = values.notna().astype(float)
    s = s - self_v
    c = c - self_c
    if stat == "sum":
        return np.where(c > 0, s, np.nan)
    return np.where(c > 0, s / c.replace(0, np.nan), np.nan)


def _loo_climatology(df: pd.DataFrame, value_col: str, keys: list[str]) -> pd.DataFrame:
    """Климатнорма по (keys + бин сезона), посчитанная БЕЗ текущего года.

    Leave-one-year-out, чтобы норма не подсматривала в тот сезон, который восстанавливаем.
    Если в текущем году в этом бине не было наблюдений, норма берётся по всем остальным годам,
    а не становится NaN.
    """
    d = df[keys + ["year", "doy_bin", value_col]].dropna(subset=[value_col])
    total = d.groupby(keys + ["doy_bin"], observed=True)[value_col].agg(
        tot_sum="sum", tot_cnt="count", tot_sq=lambda s: float((s ** 2).sum())
    ).reset_index()
    by_year = d.groupby(keys + ["doy_bin", "year"], observed=True)[value_col].agg(
        yr_sum="sum", yr_cnt="count", yr_sq=lambda s: float((s ** 2).sum())
    ).reset_index()
    grid = df[keys + ["doy_bin", "year"]].drop_duplicates()
    m = grid.merge(total, on=keys + ["doy_bin"], how="left")
    m = m.merge(by_year, on=keys + ["doy_bin", "year"], how="left")
    m["yr_sum"] = m["yr_sum"].fillna(0.0)
    m["yr_cnt"] = m["yr_cnt"].fillna(0.0)
    m["yr_sq"] = m["yr_sq"].fillna(0.0)
    loo_cnt = m["tot_cnt"] - m["yr_cnt"]
    loo_sum = m["tot_sum"] - m["yr_sum"]
    loo_sq = m["tot_sq"] - m["yr_sq"]
    mean = loo_sum / loo_cnt.replace(0, np.nan)
    var = (loo_sq / loo_cnt.replace(0, np.nan)) - mean ** 2
    out = pd.DataFrame({
        "clim_mean": mean,
        "clim_std": np.sqrt(var.clip(lower=0)),
        "clim_n": loo_cnt,
    }, index=m.index)
    for k in keys:
        out[k] = m[k]
    out["doy_bin"] = m["doy_bin"]
    out["year"] = m["year"]
    return out


def _harmonic_fit(df: pd.DataFrame, value_col: str, groups: pd.Series,
                  n_harm: int = 3) -> np.ndarray:
    """Подгоняет гладкую сезонную кривую по видимым точкам сезона и берёт её значение.

    Локальная интерполяция знает только соседей; гармоники видят форму всего сезона
    целиком, поэтому на длинных дырках дают опору там, где соседей просто нет.
    """
    out = np.full(len(df), np.nan)
    doy = df["doy"].to_numpy(dtype=float)
    y = df[value_col].to_numpy(dtype=float)
    for _, idx in df.groupby(groups, observed=True).indices.items():
        obs = ~np.isnan(y[idx])
        if obs.sum() < 2 * n_harm + 2:
            continue
        ang = 2 * np.pi * doy[idx] / 365.25
        cols = [np.ones(len(idx))] + [f(k * ang) for k in range(1, n_harm + 1)
                                      for f in (np.sin, np.cos)]
        A = np.column_stack(cols)
        try:
            coef, *_ = np.linalg.lstsq(A[obs], y[idx][obs], rcond=None)
            fit = A @ coef
        except np.linalg.LinAlgError:
            continue
        # период гармоник — год, а сезон длится всего 213 дней, поэтому на краях
        # подгонка улетает в бесконечность; держим её в пределах наблюдений сезона
        lo = float(np.nanmin(y[idx][obs])) - 0.15
        hi = float(np.nanmax(y[idx][obs])) + 0.15
        out[idx] = np.clip(fit, max(lo, -1.0), min(hi, 1.0))
    return out


def _date_anomaly(df: pd.DataFrame, value_col: str, anom_base: np.ndarray,
                  keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Что творится у ДРУГИХ полигонов в эту же дату (leave-one-polygon-out).

    Поля лежат в одном регионе и переживают одну и ту же погоду: если у соседей
    в этот день просадка относительно их собственной нормы, скорее всего она и здесь.
    Своя строка из среднего исключается, иначе это утечка.
    """
    v = df[value_col].to_numpy(dtype=float) - anom_base
    ok = ~np.isnan(v)
    tmp = pd.DataFrame({"v": np.where(ok, v, 0.0), "c": ok.astype(float)})
    for k in keys:
        tmp[k] = df[k].to_numpy()
    g = tmp.groupby(keys, observed=True)
    s = g["v"].transform("sum") - tmp["v"]
    c = g["c"].transform("sum") - tmp["c"]
    mean = np.where(c > 0, s / np.where(c == 0, 1, c), np.nan)
    return mean, c.to_numpy()


def _analog_years(df: pd.DataFrame, value_col: str, n_top: int = 3):
    """Ищет для текущего сезона похожие сезоны того же поля и берёт их значения.

    Климатнорма усредняет все годы подряд, теряя различие между засушливым и
    влажным сезоном. Здесь наоборот: сравниваем текущий сезон по видимым точкам
    с каждым другим годом того же полигона и опираемся на самые похожие.
    Утечки нет: текущий год в кандидаты не входит, а его собственное значение
    в целевой строке скрыто.
    """
    n = len(df)
    out_w = np.full(n, np.nan)
    out_best = np.full(n, np.nan)
    out_sim = np.full(n, np.nan)
    out_n = np.zeros(n)

    doy = df["doy"].to_numpy()
    y = df[value_col].to_numpy(dtype=float)
    lo, hi = 1, 367
    width = hi - lo

    for _, pidx in df.groupby(df["anon_polygon_id"], observed=True).indices.items():
        years = df["year"].to_numpy()[pidx]
        uy = np.unique(years)
        if len(uy) < 2:
            continue
        # суточная сетка значений по каждому году: линейная интерполяция видимых точек
        grid = {}
        for yr in uy:
            m = years == yr
            idx = pidx[m]
            v = pd.Series(y[idx], index=doy[idx]).groupby(level=0).mean()
            if v.notna().sum() < 3:
                continue
            full = pd.Series(np.nan, index=np.arange(lo, hi), dtype=float)
            full.loc[v.dropna().index] = v.dropna().to_numpy()
            grid[yr] = full.interpolate(limit_direction="both").to_numpy()
        if len(grid) < 2:
            continue

        for yr in uy:
            if yr not in grid:
                continue
            m = years == yr
            idx = pidx[m]
            obs_doy = doy[idx][~np.isnan(y[idx])]
            if len(obs_doy) < 4:
                continue
            cur = grid[yr]
            pos = obs_doy - lo
            sims, cands = [], []
            for yr2, g2 in grid.items():
                if yr2 == yr:
                    continue
                d = cur[pos] - g2[pos]
                sims.append(float(np.sqrt(np.mean(d ** 2))))
                cands.append(yr2)
            if not cands:
                continue
            sims = np.asarray(sims)
            order = np.argsort(sims)[:n_top]
            w = 1.0 / (sims[order] + 0.02)
            w = w / w.sum()
            stack = np.vstack([grid[cands[i]] for i in order])
            blended = (w[:, None] * stack).sum(axis=0)
            p = doy[idx] - lo
            out_w[idx] = blended[p]
            out_best[idx] = grid[cands[order[0]]][p]
            out_sim[idx] = sims[order[0]]
            out_n[idx] = len(cands)
    return out_w, out_best, out_sim, out_n


# ---------------------------------------------------------------- основной билдер


def build_features(masked: pd.DataFrame, include_harm: bool = False) -> pd.DataFrame:
    """Строит матрицу признаков по замаскированной копии данных."""
    df = masked.sort_values(["anon_polygon_id", "date"]).reset_index(drop=True).copy()
    df["doy_bin"] = (df["doy"] // DOY_BIN).astype(np.int16)
    daynum = (df["date"].values.astype("datetime64[D]").astype(np.int64)).astype(np.float64)
    season = df["anon_polygon_id"].astype(str) + "_" + df["year"].astype(str)
    poly = df["anon_polygon_id"].astype(str)

    F = pd.DataFrame(index=df.index)
    F["doy"] = df["doy"]
    F["year"] = df["year"]
    F["crop_type"] = df["crop_type"]

    # --- сезонная форма: гармоники по дню года
    ang = 2 * np.pi * df["doy"] / 365.25
    for k in (1, 2, 3):
        F[f"sin{k}"] = np.sin(k * ang)
        F[f"cos{k}"] = np.cos(k * ang)

    # --- соседние наблюдения primary_ndvi внутри сезона
    v = df["primary_ndvi"]
    pv, nx, dtp, dtn, pi, ni = _prev_next(v, season, daynum)
    F["prev_ndvi"], F["next_ndvi"] = pv, nx
    F["dt_prev"], F["dt_next"] = dtp, dtn
    F["gap_len"] = dtp + dtn
    F["dt_min"] = np.fmin(dtp, dtn)
    F["dt_ratio"] = dtp / (dtp + dtn)

    # линейная интерполяция — сильнейший одиночный признак и одновременно baseline
    w = dtn / (dtp + dtn)
    F["lin_interp"] = w * pv + (1 - w) * nx
    F["neighbor_mean"] = _nanmean2(pv, nx)
    F["neighbor_diff"] = nx - pv
    F["neighbor_slope"] = (nx - pv) / (dtp + dtn)

    # вторые соседи -> локальная кривизна и тренд
    def second(pos_arr, base):
        out = np.full(len(df), np.nan)
        ok = pos_arr >= 0
        out[ok] = base[pos_arr[ok]]
        return out

    F["prev2_ndvi"] = second(pi, pv)
    F["next2_ndvi"] = second(ni, nx)
    F["slope_before"] = (pv - F["prev2_ndvi"]) / np.maximum(dtp, 1)
    F["slope_after"] = (F["next2_ndvi"] - nx) / np.maximum(dtn, 1)
    F["curvature"] = F["slope_after"] - F["slope_before"]
    # экстраполяция с двух сторон и их среднее
    F["extrap_fwd"] = pv + F["slope_before"] * dtp
    F["extrap_bwd"] = nx - F["slope_after"] * dtn
    F["extrap_mean"] = _nanmean2(F["extrap_fwd"].to_numpy(), F["extrap_bwd"].to_numpy())

    # --- скользящие окна NDVI внутри сезона (без самой строки)
    for wnd in (10, 20, 45):
        F[f"ndvi_roll{wnd}"] = _roll(v, season, wnd)
    # статистики сезона/полигона — без самой строки (см. _loo_stat)
    F["ndvi_season_mean"] = _loo_stat(v, season, "mean")
    F["ndvi_season_std"] = _loo_stat(v, season, "std")
    F["ndvi_season_n"] = _loo_stat(v, season, "count")
    F["ndvi_poly_mean"] = _loo_stat(v, poly, "mean")

    # --- климатнорма, leave-one-year-out: по полигону, по культуре, глобально
    for name, keys in (("poly", ["anon_polygon_id"]), ("crop", ["crop_type"]), ("all", [])):
        if keys:
            clim = _loo_climatology(df, "primary_ndvi", keys)
            merged = df[keys + ["doy_bin", "year"]].merge(clim, on=keys + ["doy_bin", "year"], how="left")
        else:
            tmp = df.assign(_g=0)
            clim = _loo_climatology(tmp, "primary_ndvi", ["_g"])
            merged = tmp[["_g", "doy_bin", "year"]].merge(clim, on=["_g", "doy_bin", "year"], how="left")
        F[f"clim_{name}_mean"] = merged["clim_mean"].to_numpy()
        F[f"clim_{name}_std"] = merged["clim_std"].to_numpy()
        F[f"clim_{name}_n"] = merged["clim_n"].to_numpy()

    # отклонения соседей от нормы: переносим локальную аномалию сезона на целевую дату
    F["prev_anom"] = pv - F["clim_poly_mean"]
    F["next_anom"] = nx - F["clim_poly_mean"]
    F["anom_mean"] = _nanmean2(F["prev_anom"].to_numpy(), F["next_anom"].to_numpy())
    F["clim_plus_anom"] = F["clim_poly_mean"] + F["anom_mean"]
    F["season_shift"] = F["ndvi_season_mean"] - F["ndvi_poly_mean"]

    # --- другие сенсоры: ближайшие видимые значения
    for col in ("s2_ndvi", "landsat_ndvi", "modis_ndvi", "s2_evi", "modis_evi", "s2_ndwi"):
        p2, n2, d2p, d2n, _, _ = _prev_next(df[col], season, daynum)
        wc = d2n / (d2p + d2n)
        F[f"{col}_interp"] = wc * p2 + (1 - wc) * n2
        F[f"{col}_dtmin"] = np.fmin(d2p, d2n)
    F["sensor_spread"] = F[["s2_ndvi_interp", "landsat_ndvi_interp", "modis_ndvi_interp"]].std(axis=1)
    F["sensor_mean"] = F[["s2_ndvi_interp", "landsat_ndvi_interp", "modis_ndvi_interp"]].mean(axis=1)
    F["modis_minus_lin"] = F["modis_ndvi_interp"] - F["lin_interp"]

    # Высокодетальный оптический сенсор (S2 или Landsat со сдвигом калибровки):
    # спасает 2010-2016 гг., где Sentinel-2 ещё не летал
    F["optical_hr_interp"] = F["s2_ndvi_interp"].fillna(F["landsat_ndvi_interp"] - 0.037)
    F["optical_hr_dtmin"] = np.where(F["s2_ndvi_interp"].notna(), F["s2_ndvi_dtmin"], F["landsat_ndvi_dtmin"])
    F["optical_hr_minus_lin"] = F["optical_hr_interp"] - F["lin_interp"]

    # --- погода ERA5: у целевой строки замаскирована, берём окна вокруг
    for col, short in (("era5_temp_c", "temp"), ("era5_precip_mm", "precip")):
        s = df[col]
        for wnd in (7, 21, 60):
            F[f"{short}_roll{wnd}"] = _roll(s, season, wnd, stat="mean" if short == "temp" else "sum")
        F[f"{short}_season_mean"] = s.groupby(season, observed=True).transform("mean")
        # аномалия погоды сезона относительно средней по полигону за все годы
        F[f"{short}_season_anom"] = (F[f"{short}_season_mean"]
                                     - s.groupby(poly, observed=True).transform("mean"))
    # накопленные тепло и осадки с начала сезона (косвенно — фаза развития)
    g = df.groupby(season, observed=True)
    temp_filled = df["era5_temp_c"].ffill().bfill()
    precip_filled = df["era5_precip_mm"].fillna(0.0)
    F["gdd_cum"] = (temp_filled - 5).clip(lower=0).groupby(season, observed=True).cumsum()
    F["precip_cum"] = precip_filled.groupby(season, observed=True).cumsum()
    F["dry_days_30"] = _roll(df["era5_precip_mm"].lt(0.5).astype(float), season, 15, stat="mean")
    F["heat_days_30"] = _roll(df["era5_temp_c"].gt(28).astype(float), season, 15, stat="mean")

    # --- форма сезона целиком: гармоническая подгонка по видимым точкам (вредит на краях)
    if include_harm:
        F["harm_fit"] = _harmonic_fit(df, "primary_ndvi", season, n_harm=3)
        F["harm_fit2"] = _harmonic_fit(df, "primary_ndvi", season, n_harm=2)
        F["harm_minus_lin"] = F["harm_fit"] - F["lin_interp"]
        F["harm_minus_clim"] = F["harm_fit"] - F["clim_poly_mean"]

    # --- пространственный сигнал: соседние поля в ту же дату
    base = F["clim_poly_mean"].to_numpy(dtype=float)
    for tag, keys in (("all", ["date"]), ("crop", ["date", "crop_type"])):
        m, c = _date_anomaly(df, "primary_ndvi", base, keys)
        F[f"date_anom_{tag}"] = m
        F[f"date_anom_{tag}_n"] = c
    F["clim_plus_date_anom"] = F["clim_poly_mean"] + F["date_anom_all"]
    F["date_anom_diff"] = F["date_anom_crop"] - F["date_anom_all"]
    # то же по окну +-3 дня: спутники снимают не каждый день, точных совпадений мало
    win = df.assign(_w=(daynum // 3).astype(np.int64))
    m, c = _date_anomaly(win.assign(date=win["_w"]), "primary_ndvi", base, ["date"])
    F["date_anom_win"] = m
    F["date_anom_win_n"] = c

    # --- годы-аналоги: сезоны того же поля с похожей динамикой
    aw, ab, asim, an = _analog_years(df, "primary_ndvi")
    F["analog_ndvi"] = aw
    F["analog_best"] = ab
    F["analog_sim"] = asim
    F["analog_n"] = an
    F["analog_minus_clim"] = F["analog_ndvi"] - F["clim_poly_mean"]
    F["analog_minus_lin"] = F["analog_ndvi"] - F["lin_interp"]

    # --- служебное
    F["days_from_season_start"] = df["doy"] - g["doy"].transform("min")
    F["n_ref_years"] = df["n_reference_years"]
    return F


FEATURE_META = {
    "лаги/соседи": ["prev_ndvi", "next_ndvi", "dt_prev", "dt_next", "gap_len", "lin_interp",
                    "neighbor_slope", "prev2_ndvi", "next2_ndvi", "curvature", "extrap_mean"],
    "сезон": ["doy", "sin1", "cos1", "sin2", "cos2", "sin3", "cos3", "days_from_season_start"],
    "окна NDVI": ["ndvi_roll10", "ndvi_roll20", "ndvi_roll45", "ndvi_season_mean", "ndvi_season_std"],
    "климатнорма": ["clim_poly_mean", "clim_crop_mean", "clim_all_mean", "prev_anom", "clim_plus_anom"],
    "кросс-сенсор": ["s2_ndvi_interp", "landsat_ndvi_interp", "modis_ndvi_interp", "sensor_spread"],
    "погода": ["temp_roll7", "precip_roll21", "gdd_cum", "precip_cum", "dry_days_30", "heat_days_30"],
}
