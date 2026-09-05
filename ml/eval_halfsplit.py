#!/usr/bin/env python3
"""Сколько стоит аугментация ответами: полусплит по полигонам test1.

    python eval_halfsplit.py --train train_dataset.csv \
        --test-features test1_features.csv --truth private_test_ground_truth.csv \
        --rounds 15

Проблема: ответы организаторов можно потратить либо на замер, либо на обучение,
но не на то и другое сразу. evaluate_truth.py тратит их на замер. Здесь они
делятся: полигоны test1 режутся пополам, ответы половины A вписываются в данные
как обычные наблюдения, метрика считается на скрытых точках половины B.

Два прогона на одних и тех же точках B:

    control   — ответы A не вписаны (как в evaluate_truth.py)
    augmented — ответы A вписаны в обучение

Разница между ними и есть цена аугментации. Она же — холдаут, который переживёт
добавление labeled_test1.csv в финальную модель: точки B можно перемерить
и после.

Замер консервативный. A и B — разные полигоны, поэтому измеряется только эффект
«больше размеченных полей в обучении», без переноса внутри полигона. В финальной
модели 20 из 78 полигонов test1 совпадают с полигонами test2, и там добавляется
ещё и внутриполигонный перенос, которого здесь нет.

Второе применение — проверка дособранных через GEE полей:

    python eval_halfsplit.py ... --mode external --extra external_train.csv

Тогда ответы A вписаны в обоих прогонах, а различается наличие внешних данных.
Половина B — единственный холдаут, переживший раздачу ответов, поэтому решать
«годится ли сбор» надо именно на ней, а не на синтетических дырках.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from ndvi_ml.data import load_raw, mask_rows, observed_mask
from ndvi_ml.experiment import build_all_features, make_training_set
from ndvi_ml.metrics import core_metrics, phase_bucket, sliced_report
from ndvi_ml.model import NdviModel

THRESHOLD = 0.10

# Консоль Windows живёт в cp1251/cp866 и роняет скрипт на любом символе вне
# кодировки: прогон, посчитавший обе модели, падал на печати «ΔRMSE» и не
# успевал сохранить halfsplit_metrics.csv. Пятнадцать минут счёта в мусор
# из-за одной буквы, поэтому вывод переводим в utf-8 с заменой непечатаемого.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def gap_score(rmse: float) -> float:
    return round(30 * max(0.0, 1 - rmse / THRESHOLD), 2)


def split_polygons(df: pd.DataFrame, target: np.ndarray, known: set, seed: int):
    """Полигоны с контрольными точками — пополам, отдельно знакомые и новые.

    Стратификация обязательна: знакомые по train полигоны восстанавливаются
    заметно лучше новых, и перекос состава между половинами смешался бы
    с эффектом аугментации.
    """
    rng = np.random.default_rng(seed)
    polys = pd.Index(sorted(df.loc[target, "anon_polygon_id"].unique()))
    a, b = [], []
    for grp in (True, False):
        sel = [p for p in polys if (p in known) == grp]
        sel = list(rng.permutation(sel))
        half = len(sel) // 2
        a += sel[:half]
        b += sel[half:]
    return set(a), set(b)


def run(df: pd.DataFrame, base_hidden: np.ndarray, eval_rows: np.ndarray,
        rounds: int, seed: int) -> np.ndarray:
    """Обучает и возвращает предсказания на eval_rows.

    base_hidden скрыт всегда: и при счёте признаков, и при наборе обучающих
    примеров. Это точки, ответы на которые модель не должна увидеть никак.
    """
    F = build_all_features(mask_rows(df, base_hidden))
    X, y = make_training_set(df, base_hidden, observed_mask(df) & ~base_hidden,
                             n_rounds=rounds, seed=seed)
    print(f"  обучающих примеров: {len(X)}")
    model = NdviModel(seed=seed).fit(X, y)
    return model.predict(F)[eval_rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test-features", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", default="reports_halfsplit")
    ap.add_argument("--mode", choices=("answers", "external"), default="answers",
                    help="что проверяем: цену ответов test1 или цену внешних данных")
    ap.add_argument("--extra", nargs="*", default=None,
                    help="дособранные полигоны (external_train.csv); нужен для --mode external")
    a = ap.parse_args()

    if a.mode == "external" and not a.extra:
        raise SystemExit("--mode external без --extra бессмысленен")

    from pathlib import Path
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)

    known = set(pd.read_csv(a.train, usecols=["anon_polygon_id"]).anon_polygon_id)
    truth = pd.read_csv(a.truth)
    tcol = next(c for c in ("primary_ndvi_true", "primary_ndvi") if c in truth.columns)

    def frame(extra):
        """Собирает датасет и маски. Внешние строки меняют индексацию, поэтому
        маски считаются заново для каждого варианта, а не переиспользуются."""
        d = load_raw(a.train, a.test_features, extra_paths=extra)
        tg = d["is_target"].to_numpy()
        key = pd.DataFrame({
            "anon_polygon_id": d["anon_polygon_id"],
            "date": pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d"),
        })
        answers = key.merge(truth[["anon_polygon_id", "date", tcol]],
                            on=["anon_polygon_id", "date"], how="left")[tcol].to_numpy()
        return d, tg, answers

    df, target, ans = frame(None)
    pa, pb = split_polygons(df, target, known, a.seed)

    def masks(d, tg, answers):
        ra = tg & d["anon_polygon_id"].isin(pa).to_numpy() & ~np.isnan(answers)
        rb = tg & d["anon_polygon_id"].isin(pb).to_numpy() & ~np.isnan(answers)
        return ra, rb

    rows_a, rows_b = masks(df, target, ans)

    print(f"данные: {len(df)} строк, {df.anon_polygon_id.nunique()} полигонов")
    print(f"половина A (уходит в обучение): {len(pa)} полигонов, {int(rows_a.sum())} ответов")
    print(f"половина B (на ней метрика):    {len(pb)} полигонов, {int(rows_b.sum())} ответов")

    y_true = ans[rows_b]

    if a.mode == "answers":
        print("\n[1/2] control — ответы A НЕ вписаны")
        pred_ctl = run(df, target, rows_b, a.rounds, a.seed)

        print("\n[2/2] augmented — ответы A вписаны в обучение")
        df_aug = df.copy()
        df_aug.loc[rows_a, "primary_ndvi"] = ans[rows_a]
        # A перестала быть загадкой: это обычные наблюдения. Скрытыми остаются только B
        pred_aug = run(df_aug, rows_b, rows_b, a.rounds, a.seed)
    else:
        # ответы A вписаны в обоих прогонах, различаются только внешние данные
        print("\n[1/2] control — ответы A вписаны, внешних данных нет")
        df_c = df.copy()
        df_c.loc[rows_a, "primary_ndvi"] = ans[rows_a]
        pred_ctl = run(df_c, rows_b, rows_b, a.rounds, a.seed)

        print(f"\n[2/2] augmented — плюс внешние данные: {', '.join(a.extra)}")
        df_e, tg_e, ans_e = frame(a.extra)
        ra_e, rb_e = masks(df_e, tg_e, ans_e)
        df_e.loc[ra_e, "primary_ndvi"] = ans_e[ra_e]
        n_ext = int((df_e["source"] == "external").sum())
        print(f"  внешних строк: {n_ext}, полигонов "
              f"{df_e.loc[df_e.source == 'external', 'anon_polygon_id'].nunique()}")
        pred_aug = run(df_e, rb_e, rb_e, a.rounds, a.seed)
        assert np.allclose(ans_e[rb_e], y_true), "половина B разъехалась между прогонами"

    rows = []
    for name, p in (("control", pred_ctl), ("augmented", pred_aug)):
        m = core_metrics(y_true, p)
        m["method"] = name
        m["GapScore"] = gap_score(m["RMSE"])
        rows.append(m)
    table = pd.DataFrame(rows).set_index("method")
    cols = ["n", "RMSE", "GapScore", "MAE", "MedAE", "R2", "bias", "within_0.05"]
    what = "ответов test1" if a.mode == "answers" else "внешних данных"
    print(f"\n=== цена {what}, метрика на половине B ===")
    print(table[cols].round(5).to_string())

    d_rmse = float(table.loc["augmented", "RMSE"] - table.loc["control", "RMSE"])
    d_score = float(table.loc["augmented", "GapScore"] - table.loc["control", "GapScore"])
    verdict = "помогает" if d_rmse < 0 else "не помогает"
    print(f"\nΔRMSE {d_rmse:+.5f}  ΔGapScore {d_score:+.2f}  -> добавление {what} {verdict}")
    print("порог измеримости из NIGHT_LOG: 0.0005 — меньше считать шумом")

    table.round(5).to_csv(out / "halfsplit_metrics.csv")

    ev = pd.DataFrame({
        "anon_polygon_id": df.loc[rows_b, "anon_polygon_id"].to_numpy(),
        "date": pd.to_datetime(df.loc[rows_b, "date"]).dt.strftime("%Y-%m-%d"),
        "y": y_true, "pred_control": pred_ctl, "pred_augmented": pred_aug,
        "crop_type": df.loc[rows_b, "crop_type"].astype(str).to_numpy(),
        "year": df.loc[rows_b, "year"].to_numpy(),
        "doy": df.loc[rows_b, "doy"].to_numpy(),
    })
    ev["группа"] = np.where(ev.anon_polygon_id.isin(known), "есть в train", "новый полигон")
    ev["phase"] = phase_bucket(ev["doy"])
    ev.to_csv(out / "halfsplit_predictions.csv", index=False)

    for by in ("группа", "crop_type", "phase"):
        for name, col in (("control", "pred_control"), ("augmented", "pred_augmented")):
            tab = sliced_report(ev.assign(pred=ev[col]), by)
            if tab.empty:
                continue
            tab.insert(0, "run", name)
            tab.to_csv(out / f"halfsplit_slice_{by}_{name}.csv")

    pd.Series(sorted(pa)).to_csv(out / "polygons_A_train.csv", index=False, header=["anon_polygon_id"])
    pd.Series(sorted(pb)).to_csv(out / "polygons_B_holdout.csv", index=False, header=["anon_polygon_id"])
    print(f"\nотчёты в {out}/")
    print("полигоны B — это холдаут: их ответы никуда не уходили, метрику можно повторить")


if __name__ == "__main__":
    main()
