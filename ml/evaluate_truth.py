#!/usr/bin/env python3
"""Честный замер на реальных ответах организаторов — не на синтетических дырках.

    python evaluate_truth.py --train train_dataset.csv \
        --test-features test1_features.csv --truth private_test_ground_truth.csv \
        --rounds 15

Обучает модель ровно так же, как predict_submission.py, но предсказывает те
контрольные точки, ответы на которые известны, и считает настоящие RMSE и GapScore.
Это лучшая доступная оценка: она измеряет то же самое, что платформа.

НЕ передавай сюда --extra с ответами на эти же точки: получится обучение на
ответах, и метрика соврёт.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ndvi_ml.baselines import BASELINES
from ndvi_ml.data import load_raw, mask_rows, observed_mask
from ndvi_ml.experiment import build_all_features, make_training_set
from ndvi_ml.metrics import core_metrics, gap_bucket, phase_bucket, sliced_report
from ndvi_ml.model import NdviModel

THRESHOLD = 0.10   # порог GapScore из постановки


def gap_score(rmse: float) -> float:
    return round(30 * max(0.0, 1 - rmse / THRESHOLD), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test-features", required=True, help="набор, ответы на который известны")
    ap.add_argument("--truth", required=True)
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--extra", nargs="*", default=None,
                    help="дополнительные размеченные данные (НЕ ответы на эти же точки)")
    ap.add_argument("--outdir", default="reports_truth")
    a = ap.parse_args()

    from pathlib import Path
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)

    df = load_raw(a.train, a.test_features, extra_paths=a.extra)
    target = df["is_target"].to_numpy()
    print(f"данные: {len(df)} строк, {df.anon_polygon_id.nunique()} полигонов, "
          f"{int(observed_mask(df).sum())} наблюдений, {int(target.sum())} контрольных точек")

    masked = mask_rows(df, target)
    F = build_all_features(masked)
    X, y = make_training_set(df, target, observed_mask(df), n_rounds=a.rounds, seed=a.seed)
    print(f"обучающих примеров ({a.rounds} раундов маскирования): {len(X)}")
    model = NdviModel(seed=a.seed).fit(X, y)

    pred = model.predict(F)
    got = pd.DataFrame({
        "anon_polygon_id": df.loc[target, "anon_polygon_id"].to_numpy(),
        "date": pd.to_datetime(df.loc[target, "date"]).dt.strftime("%Y-%m-%d"),
        "pred": pred[target],
        "pred_linear": BASELINES["linear"](masked, F)[target],
        "gap_len": F.loc[target, "gap_len"].to_numpy(),
        "crop_type": df.loc[target, "crop_type"].astype(str).to_numpy(),
        "year": df.loc[target, "year"].to_numpy(),
        "doy": df.loc[target, "doy"].to_numpy(),
    })

    truth = pd.read_csv(a.truth)
    tcol = next(c for c in ("primary_ndvi_true", "primary_ndvi") if c in truth.columns)
    ev = got.merge(truth[["anon_polygon_id", "date", tcol]], on=["anon_polygon_id", "date"])
    ev = ev.rename(columns={tcol: "y"})
    if len(ev) != len(got):
        print(f"ВНИМАНИЕ: сопоставилось {len(ev)} из {len(got)} контрольных точек")

    known = set(pd.read_csv(a.train, usecols=["anon_polygon_id"]).anon_polygon_id)
    ev["группа"] = np.where(ev.anon_polygon_id.isin(known), "есть в train", "новый полигон")

    print("\n=== НАСТОЯЩИЕ метрики на ответах организаторов ===")
    rows = []
    for name, col in (("lightgbm", "pred"), ("линейная интерполяция", "pred_linear")):
        m = core_metrics(ev["y"], ev[col])
        m["method"] = name
        m["GapScore"] = gap_score(m["RMSE"])
        rows.append(m)
    table = pd.DataFrame(rows).set_index("method")
    cols = ["n", "RMSE", "GapScore", "MAE", "MedAE", "R2", "bias", "within_0.05", "within_0.10"]
    print(table[cols].round(5).to_string())
    table.round(5).to_csv(out / "truth_metrics.csv")

    ev["pred_col"] = ev["pred"]
    frame = ev.rename(columns={"pred": "pred_keep"}).assign(pred=ev["pred"])
    frame["gap_bucket"] = gap_bucket(frame["gap_len"])
    frame["phase"] = phase_bucket(frame["doy"])
    for by in ("группа", "crop_type", "gap_bucket", "phase", "year"):
        tab = sliced_report(frame, by)
        if tab.empty:
            continue
        print(f"\n=== разрез: {by} ===")
        print(tab.round(4).to_string())
        tab.to_csv(out / f"truth_slice_{by}.csv")

    ev.drop(columns=["pred_col"]).to_csv(out / "truth_predictions.csv", index=False)
    best = float(table.loc["lightgbm", "RMSE"])
    print(f"\nИТОГ: RMSE {best:.5f}, GapScore {gap_score(best)} из 30")
    print(f"отчёты в {out}/")


if __name__ == "__main__":
    main()
