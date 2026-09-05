#!/usr/bin/env bash
# Полный прогон под расклад с двумя тестами и ответами на первый.
#
#   ./run_final.sh train_dataset.csv test1_features.csv ground_truth.csv test2_features.csv
#
# test1_features.csv  — первый тестовый набор (ответы на него известны)
# ground_truth.csv    — ответы организаторов на test1
# test2_features.csv  — новый тестовый набор, для него делается сабмит
set -euo pipefail

TRAIN="${1:-train_dataset.csv}"
TEST1="${2:-test1_features.csv}"
TRUTH="${3:-private_test_ground_truth.csv}"
TEST2="${4:-test_features.csv}"

ROUNDS="${ROUNDS:-15}"          # раундов в честном замере
FINAL_ROUNDS="${FINAL_ROUNDS:-40}"   # раундов в финальной модели

for f in "$TRAIN" "$TEST1" "$TRUTH" "$TEST2"; do
  [ -f "$f" ] || { echo "не найден файл: $f"; exit 1; }
done

echo "== 1/4 честный замер на ответах организаторов (rounds=$ROUNDS)"
# Обучение идёт на train + видимых строках test1. Ответы на контрольные точки
# в обучение НЕ попадают — иначе метрика соврёт.
python evaluate_truth.py --train "$TRAIN" --test-features "$TEST1" --truth "$TRUTH" \
    --rounds "$ROUNDS" --outdir reports_truth

echo
echo "== 2/4 сшивка test1 с ответами в размеченный датасет"
python prepare_labeled.py --features "$TEST1" --truth "$TRUTH" --out labeled_test1.csv

echo
echo "== 3/4 финальная модель и сабмит на новый тест (rounds=$FINAL_ROUNDS)"
# Здесь ответы уже можно использовать: предсказываем ДРУГИЕ контрольные точки
python predict_submission.py --train "$TRAIN" --test "$TEST2" \
    --extra labeled_test1.csv --rounds "$FINAL_ROUNDS" --outdir artifacts

echo
echo "== 4/4 графики и отчёт"
python make_charts.py --reports reports --artifacts artifacts --outdir charts 2>/dev/null || \
  echo "  (графики пропущены: нет reports/ от run_experiment.py — это нормально)"
python make_report.py 2>/dev/null || true

echo
echo "готово:"
echo "  artifacts/submission.csv    -> на платформу (колонка primary_ndvi_pred)"
echo "  artifacts/ndvi_model.pkl    -> модель для инференса и веб-сервиса"
echo "  reports_truth/truth_metrics.csv -> настоящие RMSE и GapScore"
echo "  artifacts/anomalies.csv     -> найденные аномальные периоды"
