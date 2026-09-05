#!/usr/bin/env python3
"""Финальная модель: обучение на всех доступных данных, submission.csv и аномалии.

    python predict_submission.py --train train_dataset.csv --test private_features.csv \
        --rounds 5 --outdir artifacts
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ndvi_ml.anomalies import build_series, explain, find_periods
from ndvi_ml.data import load_raw, mask_rows, observed_mask
from ndvi_ml.experiment import build_all_features, make_training_set
from ndvi_ml.model import NdviModel
from ndvi_ml.pipeline import NdviPipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--outdir", default="artifacts")
    ap.add_argument("--rounds", type=int, default=20,
                    help="раундов маскирования: 20 — оптимум для озимой пшеницы")
    ap.add_argument("--seed", type=int, default=0,
                    help="базовый seed (используется, если --seeds не указан)")
    ap.add_argument("--seeds", default="0,42,100",
                    help="список seed через запятую для ансамбля (убирает шум маскирования)")
    ap.add_argument("--extra", nargs="*", default=None,
                    help="дособранные датасеты (data_collection/): идут только в обучение")
    ap.add_argument("--blend-whittaker", type=float, default=0.0,
                    help="доля whittaker в финальном предсказании (0 = чистый LightGBM)")
    ap.add_argument("--short-gap-blend", type=float, default=0.0,
                    help="доля линейной интерполяции на сверхкоротких дырках (0.0 = выключено)")
    ap.add_argument("--catboost", action="store_true", default=True,
                    help="подмешать CatBoost в ансамбль (по умолчанию включено)")
    ap.add_argument("--no-catboost", dest="catboost", action="store_false",
                    help="отключить CatBoost")
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_raw(args.train, args.test, extra_paths=args.extra)
    target = df["is_target"].to_numpy()
    print(f"данные: {len(df)} строк, контрольных точек {int(target.sum())}")

    # контрольные строки скрыты всегда: их значений мы не знаем в принципе
    masked = mask_rows(df, target)
    F = build_all_features(masked)

    # Список сидов для ансамблирования
    if args.seeds:
        seed_list = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    else:
        seed_list = [args.seed]

    print(f"=== Запуск ансамбля по {len(seed_list)} моделям (сиды: {seed_list}) ===")
    print(f"\n[1/3] Генерация синтетических пропусков ({args.rounds} раундов)...")
    X_tr, y_tr = make_training_set(df, target, observed_mask(df),
                                   n_rounds=args.rounds, seed=seed_list[0])
    print(f"  готово: {len(X_tr)} обучающих примеров")

    print(f"\n[2/3] Обучение {len(seed_list)} моделей LightGBM (разнородные loss-функции)...")
    objectives = ["regression", "fair", "huber", "regression", "fair"]
    preds = []
    models = []
    last_model = None

    for idx, s in enumerate(seed_list):
        obj = objectives[idx % len(objectives)]
        print(f"  модель {idx + 1}/{len(seed_list)}: seed={s}, objective={obj}")
        model = NdviModel(seed=s, params={"objective": obj}).fit(X_tr, y_tr)
        p = model.predict(F)
        preds.append(p)
        models.append(model)
        last_model = model

    pred = np.mean(preds, axis=0)

    # Опциональный CatBoost
    cb_model = None
    if args.catboost:
        try:
            import catboost as cb
            print("\n[3/3] Обучение ортогональной модели CatBoost (1500 деревьев)...")
            cat_cols = ["crop_type"] if "crop_type" in X_tr.columns else []
            cb_model = cb.CatBoostRegressor(iterations=1500, learning_rate=0.03, depth=6,
                                            l2_leaf_reg=3.0, random_seed=42, verbose=False)
            cb_model.fit(X_tr[last_model.feature_names], y_tr, cat_features=cat_cols)
            cb_pred = cb_model.predict(F[last_model.feature_names])
            pred = 0.75 * pred + 0.25 * cb_pred
            print("  CatBoost успешно добавлен в ансамбль (вес 25%)")
        except ImportError:
            print("  [CatBoost] библиотека не установлена (pip install catboost), пропуск")

    if args.blend_whittaker > 0:
        w = args.blend_whittaker
        pred = (1 - w) * pred + w * F["sm_whittaker"].to_numpy()

    # Пост-процессинг: мягкий блендинг на ультракоротких пропусках (<= 2 дней)
    if args.short_gap_blend > 0 and "gap_len" in F.columns and "lin_interp" in F.columns:
        short_mask = (F["gap_len"] <= 2) & F["lin_interp"].notna()
        w = args.short_gap_blend
        pred = np.where(short_mask, (1 - w) * pred + w * F["lin_interp"].to_numpy(), pred)
        print(f"short-gap blend ({w:.0%}) применён к {int(short_mask.sum())} точкам")

    # Строгие физические границы диапазона организаторов [-0.02, 0.93]
    pred = np.clip(pred, -0.02, 0.93)
    model = last_model

    # --- submission: только контрольные строки
    # Колонка предсказания называется primary_ndvi_pred (стр. 13 постановки).
    # Не primary_ndvi и не primary_ndvi_true: platform читает файл по имени
    # колонки, и на чужом имени сабмит не засчитывается.
    sub = pd.DataFrame({
        "anon_polygon_id": df.loc[target, "anon_polygon_id"].to_numpy(),
        "date": pd.to_datetime(df.loc[target, "date"]).dt.strftime("%Y-%m-%d"),
        "primary_ndvi_pred": pred[target],
    })
    assert sub["primary_ndvi_pred"].notna().all(), "в сабмите остались пропуски"
    assert not sub.duplicated(["anon_polygon_id", "date"]).any(), "дубли пары полигон+дата"
    sub.to_csv(out / "submission.csv", index=False, encoding="utf-8")
    print(f"submission.csv: {len(sub)} строк, "
          f"NDVI {sub.primary_ndvi_pred.min():.3f}..{sub.primary_ndvi_pred.max():.3f}, "
          f"среднее {sub.primary_ndvi_pred.mean():.3f}")

    # --- полный восстановленный ряд (для веб-сервиса и задачи 2)
    filled = np.where(df["primary_ndvi"].notna(), df["primary_ndvi"], pred)
    full = pd.DataFrame({
        "anon_polygon_id": df["anon_polygon_id"],
        "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
        "crop_type": df["crop_type"].astype(str),
        "ndvi_observed": df["primary_ndvi"],
        "ndvi_filled": filled,
        "is_reconstructed": df["primary_ndvi"].isna(),
        "is_control_point": target,
    })
    full.to_csv(out / "reconstructed_series.csv", index=False)

    # --- задача 2: аномальные периоды
    series = build_series(df, filled, F)
    periods = explain(find_periods(series))
    periods.to_csv(out / "anomalies.csv", index=False)
    series.drop(columns=["doy_bin"]).to_csv(out / "series_with_zscore.csv", index=False)

    print(f"\nаномальных периодов найдено: {len(periods)}")
    if not periods.empty:
        print(periods["severity"].value_counts().to_string())
        print("\nпричины:")
        print(periods["cause"].value_counts().to_string())
        print("\nтоп-5 самых тяжёлых:")
        cols = ["anon_polygon_id", "start", "end", "days", "z_min", "crop_type", "cause"]
        print(periods.nsmallest(5, "z_min")[cols].to_string(index=False))

    imp = model.importance()
    if not imp.empty:
        imp.to_csv(out / "final_feature_importance.csv", index=False)

    pipe = NdviPipeline([m.model for m in models], last_model.feature_names,
                        config={"target": "raw", "clip": (-0.02, 0.93),
                                "short_gap_blend": args.short_gap_blend,
                                "rounds": args.rounds, "seeds": seed_list,
                                "n_features": len(last_model.feature_names)},
                        cb_model=cb_model)
    mp = pipe.save(out / "ndvi_model.pkl")
    print(f"модель сохранена: {mp} ({mp.stat().st_size // 1024} КБ, ансамбль из {len(models)} моделей)")
    print(f"\nартефакты в {out}/")


if __name__ == "__main__":
    main()
