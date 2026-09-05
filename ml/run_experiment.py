#!/usr/bin/env python3
"""Полный прогон: сценарии валидации, сравнение методов, метрики по срезам, графики.

Пример:
    python run_experiment.py --train train_dataset.csv --test private_features.csv \
        --folds 4 --rounds 3 --outdir reports
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ndvi_ml.data import load_raw
from ndvi_ml.experiment import run_scenario, slice_diagnostics
from ndvi_ml.metrics import core_metrics, worst_cases
from ndvi_ml.validation import scenario_last_season, scenario_new_polygon, scenario_random

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--outdir", default="reports")
    ap.add_argument("--folds", type=int, default=4, help="фолдов в сценарии «новый полигон»")
    ap.add_argument("--rounds", type=int, default=3, help="раундов маскирования для обучающей выборки")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--extra", nargs="*", default=None,
                    help="дособранные датасеты (data_collection/): идут только в обучение")
    ap.add_argument("--methods", default="lightgbm,linear",
                    help="что сравнивать в отчёте через запятую. Доступно: lightgbm, "
                         "lgbm+whittaker, linear, savgol, whittaker, clim+anomaly, climatology. "
                         "На признаки не влияет: сглаживатели всегда идут в модель как фичи")
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    methods_arg = tuple(m.strip() for m in args.methods.split(",") if m.strip())
    df = load_raw(args.train, args.test, extra_paths=args.extra)
    print(f"данные: {len(df)} строк, {df.anon_polygon_id.nunique()} полигонов, "
          f"{df.primary_ndvi.notna().sum()} наблюдений, {int(df.is_target.sum())} контрольных точек\n")

    scenarios = scenario_new_polygon(df, n_folds=args.folds, seed=args.seed)
    scenarios.append(scenario_last_season(df, seed=args.seed))
    scenarios.append(scenario_random(df, seed=args.seed))

    tables, details, importances = [], [], []
    for sc in scenarios:
        t0 = time.time()
        table, detail, model, X_tr = run_scenario(df, sc, n_rounds=args.rounds, seed=args.seed,
                                                  methods=methods_arg)
        imp = model.importance()
        if not imp.empty:
            imp["scenario"] = sc.name
            importances.append(imp)
        tables.append(table)
        details.append(detail)
        best = table["RMSE"].idxmin()
        print(f"[{sc.name:>18}] точек {int(table['n'].iloc[0]):5d} | обучение {len(X_tr):6d} | "
              f"лучший {best[1]:<14} RMSE={table['RMSE'].min():.4f} | {time.time() - t0:.0f}s")

    all_tab = pd.concat(tables)
    all_det = pd.concat(details, ignore_index=True)
    methods = [c[5:] for c in all_det.columns if c.startswith("pred_")]

    # --- сводка: метод × сценарий, плюс агрегат по сценарию «новый полигон»
    pivot = all_tab.reset_index().pivot(index="method", columns="scenario", values="RMSE")
    npoly = [c for c in pivot.columns if c.startswith("new_polygon")]
    pivot.insert(0, "new_polygon_avg", pivot[npoly].mean(axis=1))
    pivot = pivot.sort_values("new_polygon_avg")

    overall = []
    for m in methods:
        d = all_det[all_det.scenario.str.startswith("new_polygon")]
        r = core_metrics(d["y"], d[f"pred_{m}"])
        r["method"] = m
        overall.append(r)
    overall = pd.DataFrame(overall).set_index("method").sort_values("RMSE")

    print("\n=== RMSE: метод × сценарий ===")
    print(pivot.round(4).to_string())
    print("\n=== Полные метрики на сценарии «новый полигон» ===")
    print(overall.round(4).to_string())

    best_method = overall.index[0]
    print(f"\nлучший метод: {best_method}")

    slices = slice_diagnostics(all_det, best_method)
    for name, tab in slices.items():
        print(f"\n=== {best_method}: разрез по «{name}» ===")
        print(tab.round(4).to_string())
        tab.to_csv(out / f"slice_{name}.csv")

    # сравнение методов внутри каждого среза по длине пропуска — где кто выигрывает
    gap_cmp = []
    for m in methods:
        s = slice_diagnostics(all_det, m)["gap_bucket"]["RMSE"].rename(m)
        gap_cmp.append(s)
    gap_cmp = pd.concat(gap_cmp, axis=1)
    print("\n=== RMSE по длине пропуска: все методы ===")
    print(gap_cmp.round(4).to_string())
    gap_cmp.to_csv(out / "rmse_by_gap_length.csv")

    if importances:
        imp = (pd.concat(importances).groupby("feature")[["gain", "split"]].mean()
               .sort_values("gain", ascending=False))
        imp["gain_%"] = 100 * imp["gain"] / imp["gain"].sum()
        imp.to_csv(out / "feature_importance.csv")
        print("\n=== Топ-20 признаков по gain ===")
        print(imp.head(20).round(2).to_string())

    # --- задача 2: переносятся ли ошибки восстановления в классы аномалий
    from ndvi_ml.anomalies import classify_z
    zt = (all_det["y"] - all_det["clim_mean"]) / all_det["clim_std"].replace(0, np.nan)
    status_rows = []
    for m in methods:
        zp = (all_det[f"pred_{m}"] - all_det["clim_mean"]) / all_det["clim_std"].replace(0, np.nan)
        ok = zt.notna() & zp.notna()
        st, sp = zt[ok].map(classify_z), zp[ok].map(classify_z)
        status_rows.append({"method": m, "n": int(ok.sum()),
                            "status_accuracy_%": float((st == sp).mean() * 100),
                            "z_RMSE": float(np.sqrt(np.mean((zp[ok] - zt[ok]) ** 2))),
                            "аномалия_recall_%": float(((sp != "Штатное развитие") & (st != "Штатное развитие")).sum()
                                                       / max((st != "Штатное развитие").sum(), 1) * 100)})
    status_tab = pd.DataFrame(status_rows).set_index("method").sort_values("status_accuracy_%", ascending=False)
    print("\n=== Задача 2: класс аномалии по восстановленному значению ===")
    print(status_tab.round(3).to_string())
    status_tab.to_csv(out / "anomaly_status_agreement.csv")

    wc = worst_cases(all_det.assign(pred=all_det[f"pred_{best_method}"]), k=15)
    wc.to_csv(out / "worst_cases.csv", index=False)
    all_tab.round(5).to_csv(out / "metrics_by_scenario.csv")
    overall.round(5).to_csv(out / "metrics_overall.csv")
    pivot.round(5).to_csv(out / "rmse_pivot.csv")
    all_det.to_csv(out / "validation_predictions.csv", index=False)
    print(f"\nотчёты записаны в {out}/")


if __name__ == "__main__":
    main()
