#!/usr/bin/env python3
"""Дособранные через GEE поля -> проверка -> финальная модель -> сабмит. Одной командой.

    python run_external.py --raw ndvi_external/

`--raw` — распакованная папка из Google Drive, которую собрал
data_collection/gee_collect.py. Дальше скрипт всё делает сам:

  1. merge_external.py   — сводит выгрузку в схему организаторов
  2. validate_external.py — сверяет распределения с train_dataset.csv
  3. eval_halfsplit.py    — меряет на холдауте, помогают ли новые поля  (--check)
  4. predict_submission.py — финальная модель и сабмит

Шаг 3 — единственный честный способ узнать, годится ли сбор: половина B
полигонов test1 никогда не отдавала свои ответы в обучение, поэтому на ней
можно мерить и после того, как остальные ответы ушли в аугментацию.
Он стоит два обучения, поэтому включается флагом.

Если внешние данные окажутся хуже — не подмешивай их: собранные не по рецепту
поля живут в другом распределении и тянут модель на себя. Что именно разошлось,
покажет вывод validate_external.py.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)
    print("$ " + " ".join(cmd), flush=True)
    r = subprocess.run([sys.executable, "-W", "ignore"] + cmd)
    if r.returncode != 0:
        sys.exit(f"шаг «{title}» упал с кодом {r.returncode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True,
                    help="распакованная папка ndvi_external из Google Drive")
    ap.add_argument("--train", default="train_dataset.csv")
    ap.add_argument("--test", default="test_features.csv")
    ap.add_argument("--truth", default="private_test_ground_truth.csv")
    ap.add_argument("--test1", default="test1_features.csv")
    ap.add_argument("--labeled", default="labeled_test1.csv",
                    help="test1 с вписанными ответами; соберётся сам, если нет")
    ap.add_argument("--external", default="external_train.csv")
    ap.add_argument("--rounds", type=int, default=40, help="раундов у финальной модели")
    ap.add_argument("--check", action="store_true",
                    help="перед обучением померить на холдауте, помогают ли новые поля "
                         "(два лишних обучения, ~15 мин при rounds=15)")
    ap.add_argument("--check-rounds", type=int, default=15)
    ap.add_argument("--outdir", default="artifacts")
    a = ap.parse_args()

    raw = Path(a.raw)
    if not raw.is_dir():
        sys.exit(f"нет каталога {raw}")
    csvs = list(raw.glob("*.csv"))
    if not csvs:
        sys.exit(f"в {raw} нет ни одного CSV — распакуй архив из Drive целиком")
    if not any("fields_meta" in f.name for f in csvs):
        sys.exit("нет файла ndvi_fields_meta_b*.csv — без паспорта участков "
                 "погода не пришьётся к полям")
    print(f"{raw}: {len(csvs)} файлов")

    run(["data_collection/merge_external.py", "--raw", str(raw), "--out", a.external],
        "1/4 сведение выгрузки в схему организаторов")

    run(["data_collection/validate_external.py", "--external", a.external,
         "--reference", a.train],
        "2/4 сверка распределений с данными организаторов")

    if not Path(a.labeled).exists():
        run(["prepare_labeled.py", "--features", a.test1, "--truth", a.truth,
             "--out", a.labeled],
            "2.5/4 сшивка ответов первого теста")

    if a.check:
        run(["eval_halfsplit.py", "--train", a.train, "--test-features", a.test1,
             "--truth", a.truth, "--rounds", str(a.check_rounds),
             "--mode", "external", "--extra", a.external,
             "--outdir", "reports_halfsplit_external"],
            "3/4 холдаут: помогают ли новые поля")
        print("\nСмотри строку ΔRMSE выше. Отрицательная — новые поля помогают.")
        print("Порог измеримости 0.0005: меньше — шум, решай по MAE и по разрезам.")
        try:
            ans = input("\nпродолжать обучение с внешними данными? [Y/n] ").strip().lower()
        except EOFError:
            ans = "y"
        if ans and ans[0] == "n":
            sys.exit("остановлено. Финальную модель без внешних данных: "
                     "python predict_submission.py --train ... --extra labeled_test1.csv")

    run(["predict_submission.py", "--train", a.train, "--test", a.test,
         "--extra", a.labeled, a.external, "--rounds", str(a.rounds),
         "--outdir", a.outdir],
        "4/4 финальная модель и сабмит")

    print(f"\nготово. Сабмит: {a.outdir}/submission.csv (колонка primary_ndvi_pred)")
    print(f"модель: {a.outdir}/ndvi_model.pkl, аномалии: {a.outdir}/anomalies.csv")


if __name__ == "__main__":
    main()
