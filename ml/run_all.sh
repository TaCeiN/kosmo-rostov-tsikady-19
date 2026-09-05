#!/usr/bin/env bash
# Полный прогон: валидация -> финальная модель -> графики -> отчёт.
# Использование: ./run_all.sh [train.csv] [private_features.csv]
set -euo pipefail

TRAIN="${1:-train_dataset.csv}"
TEST="${2:-private_features.csv}"
FOLDS="${FOLDS:-4}"
ROUNDS="${ROUNDS:-15}"
FINAL_ROUNDS="${FINAL_ROUNDS:-40}"
METHODS="${METHODS:-lightgbm,linear}"

for f in "$TRAIN" "$TEST"; do
  [ -f "$f" ] || { echo "не найден файл: $f"; exit 1; }
done

echo "== 1/4 валидация и сравнение методов (folds=$FOLDS, rounds=$ROUNDS)"
python run_experiment.py --train "$TRAIN" --test "$TEST" --folds "$FOLDS" --rounds "$ROUNDS" --methods "$METHODS" --outdir reports

echo "== 2/4 финальная модель, сабмит и аномалии (rounds=$FINAL_ROUNDS)"
python predict_submission.py --train "$TRAIN" --test "$TEST" --rounds "$FINAL_ROUNDS" --outdir artifacts

echo "== 3/4 графики"
python make_charts.py --reports reports --artifacts artifacts --outdir charts

echo "== 4/4 отчёт"
python make_report.py --reports reports --artifacts artifacts --charts charts --readme README.md

echo
echo "готово:"
echo "  artifacts/submission.csv   -> на платформу"
echo "  reports/report.html        -> отчёт со всеми таблицами и графиками"
echo "  reports/REPORT.md          -> то же в markdown"
echo "  artifacts/ndvi_model.pkl   -> модель для infer.py / serve.py"
echo "  README.md                  -> блок результатов обновлён"
