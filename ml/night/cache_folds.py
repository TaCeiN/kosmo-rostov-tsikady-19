#!/usr/bin/env python3
"""Считает матрицы признаков для валидационных фолдов ОДИН раз и кладёт на диск.

Дальше любой эксперимент с гиперпараметрами/лоссами/фильтрами работает по кэшу
и занимает секунды: пересчёт признаков (самая долгая часть) больше не нужен.
Сценарии и сиды те же, что в run_experiment.py, поэтому числа сравнимы напрямую.
"""
from __future__ import annotations
import argparse, pickle, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ndvi_ml.data import load_raw, mask_rows, observed_mask
from ndvi_ml.experiment import build_all_features, make_training_set
from ndvi_ml.validation import scenario_new_polygon

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--outdir", default="cache")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=9)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    df = load_raw(a.train, a.test)
    target = df["is_target"].to_numpy()
    scenarios = scenario_new_polygon(df, n_folds=a.folds, seed=a.seed)

    for sc in scenarios:
        p = out / f"{sc.name}.pkl"
        if p.exists():
            print(f"{sc.name}: уже есть, пропускаю"); continue
        t0 = time.time()
        base_hidden = sc.hidden | target
        F_ev = build_all_features(mask_rows(df, base_hidden))
        X_tr, y_tr = make_training_set(df, base_hidden, sc.train_rows & observed_mask(df),
                                       n_rounds=a.rounds, seed=a.seed)
        ev = sc.eval_rows
        meta = pd.DataFrame({
            "anon_polygon_id": df.loc[ev, "anon_polygon_id"].to_numpy(),
            "date": df.loc[ev, "date"].to_numpy(),
            "crop_type": df.loc[ev, "crop_type"].astype(str).to_numpy(),
            "year": df.loc[ev, "year"].to_numpy(),
            "doy": df.loc[ev, "doy"].to_numpy(),
            "gap_len": F_ev.loc[ev, "gap_len"].to_numpy(),
            "clim_mean": df.loc[ev, "ndvi_climatology_mean"].to_numpy(),
            "clim_std": df.loc[ev, "ndvi_climatology_std"].to_numpy(),
        })
        with open(p, "wb") as f:
            pickle.dump({"X_tr": X_tr, "y_tr": y_tr,
                         "X_ev": F_ev[ev].reset_index(drop=True),
                         "y_ev": df.loc[ev, "primary_ndvi"].to_numpy(),
                         "meta": meta}, f, protocol=4)
        print(f"{sc.name}: обучение {len(X_tr)}, валидация {int(ev.sum())}, "
              f"{time.time()-t0:.0f}s -> {p}", flush=True)

if __name__ == "__main__":
    main()
