"""Прогон сценариев: baseline-методы против LightGBM, метрики по срезам."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .baselines import BASELINES
from .data import mask_rows, observed_mask
from .features import build_features
from .metrics import core_metrics, gap_bucket, phase_bucket, sliced_report
from .model import NdviModel
from .validation import Scenario, sample_gaps_fast

SMOOTHERS = ("savgol", "whittaker", "clim+anomaly")


def build_all_features(masked: pd.DataFrame, include_harm: bool = False) -> pd.DataFrame:
    """Признаки + предсказания классических сглаживателей как отдельные колонки.

    Стекинг: сглаживатели считаются по тем же видимым точкам, что и всё остальное,
    поэтому утечки нет, а модели проще исправлять их систематические ошибки,
    чем выводить форму кривой с нуля.
    """
    F = build_features(masked, include_harm=include_harm).copy()
    extra = {}
    for name in SMOOTHERS:
        extra[f"sm_{name}"] = BASELINES[name](masked, F)
    # whittaker на нескольких шкалах гладкости: модель сама выберет масштаб
    from .baselines import predict_whittaker
    for lam in (5.0, 30.0, 200.0):
        extra[f"sm_whit_lam{int(lam)}"] = predict_whittaker(masked, F, lam=lam)
    extra["whit_scale_diff"] = extra["sm_whit_lam5"] - extra["sm_whit_lam200"]
    extra["whit_mid_diff"] = extra["sm_whit_lam30"] - extra["sm_whit_lam200"]
    extra_df = pd.DataFrame(extra, index=F.index)
    extra_df["sm_spread"] = extra_df[[f"sm_{n}" for n in SMOOTHERS]].std(axis=1)
    extra_df["sm_minus_lin"] = extra_df["sm_whittaker"] - F["lin_interp"]
    return pd.concat([F, extra_df], axis=1)


def make_training_set(df: pd.DataFrame, base_hidden: np.ndarray, avail_rows: np.ndarray,
                      n_rounds: int = 3, seed: int = 0):
    """Обучающая выборка из искусственно спрятанных точек.

    Модель должна учиться ровно на тех признаках, которые увидит на контрольных
    строках, поэтому обучающие примеры — это тоже дырки: в каждом раунде прячем
    свои 15% и берём в обучение только их. base_hidden остаётся скрытым всегда,
    иначе валидация протечёт в обучение.
    """
    Xs, ys = [], []
    for r in range(n_rounds):
        extra = sample_gaps_fast(df, avail_rows, seed=seed + 17 * r + 1)
        hidden = extra | base_hidden
        F = build_all_features(mask_rows(df, hidden))
        rows = extra & ~base_hidden
        Xs.append(F[rows])
        ys.append(df.loc[rows, "primary_ndvi"].to_numpy())
    return pd.concat(Xs, ignore_index=True), np.concatenate(ys)


DEFAULT_METHODS = ("lightgbm", "linear")


def run_scenario(df: pd.DataFrame, sc: Scenario, n_rounds: int = 3,
                 seed: int = 0, model_params: dict | None = None,
                 methods: tuple[str, ...] = DEFAULT_METHODS):
    """Возвращает (таблица метрик по методам, покомпонентный фрейм предсказаний, модель).

    `methods` — что попадает в СРАВНЕНИЕ. На признаки это не влияет: сглаживатели
    считаются всегда, потому что идут в модель как фичи (см. build_all_features).
    """
    # 1. представление данных, которое видит решение на валидации
    masked = mask_rows(df, sc.hidden | df["is_target"].to_numpy())
    F_eval = build_all_features(masked)

    # 2. обучающая выборка — из строк, доступных этому сценарию
    avail = sc.train_rows & observed_mask(df)
    X_tr, y_tr = make_training_set(df, sc.hidden | df["is_target"].to_numpy(), avail,
                                   n_rounds=n_rounds, seed=seed)
    model = NdviModel(params=model_params, seed=seed).fit(X_tr, y_tr)

    ev = sc.eval_rows
    y = df.loc[ev, "primary_ndvi"].to_numpy()
    preds = {name: fn(masked, F_eval)[ev] for name, fn in BASELINES.items() if name in methods}
    if "lightgbm" in methods:
        preds["lightgbm"] = model.predict(F_eval[ev])
    if "lgbm+whittaker" in methods:
        lg = preds.get("lightgbm", model.predict(F_eval[ev]))
        preds["lgbm+whittaker"] = 0.7 * lg + 0.3 * BASELINES["whittaker"](masked, F_eval)[ev]

    rows = []
    for name, p in preds.items():
        m = core_metrics(y, p)
        m["method"] = name
        m["scenario"] = sc.name
        rows.append(m)
    table = pd.DataFrame(rows).set_index(["scenario", "method"])

    detail = pd.DataFrame({
        "anon_polygon_id": df.loc[ev, "anon_polygon_id"].to_numpy(),
        "date": df.loc[ev, "date"].to_numpy(),
        "crop_type": df.loc[ev, "crop_type"].astype(str).to_numpy(),
        "year": df.loc[ev, "year"].to_numpy(),
        "doy": df.loc[ev, "doy"].to_numpy(),
        "gap_len": F_eval.loc[ev, "gap_len"].to_numpy(),
        # климатнорма самих организаторов — чтобы проверить, как ошибки
        # интерполяции переносятся в классы аномалий (задача 2)
        "clim_mean": df.loc[ev, "ndvi_climatology_mean"].to_numpy(),
        "clim_std": df.loc[ev, "ndvi_climatology_std"].to_numpy(),
        "y": y,
        "scenario": sc.name,
    })
    for name, p in preds.items():
        detail[f"pred_{name}"] = p
    return table, detail, model, X_tr


def slice_diagnostics(detail: pd.DataFrame, method: str) -> dict[str, pd.DataFrame]:
    """RMSE/MAE/R2 в разрезах: сценарий, культура, длина пропуска, фаза сезона, год."""
    f = detail.copy()
    f["pred"] = f[f"pred_{method}"]
    f["gap_bucket"] = gap_bucket(f["gap_len"])
    f["phase"] = phase_bucket(f["doy"])
    return {by: sliced_report(f, by) for by in
            ("scenario", "crop_type", "gap_bucket", "phase", "year")}
