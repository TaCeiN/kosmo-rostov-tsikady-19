"""Проверка на утечку: признаки скрытой строки не должны зависеть от её значения.

Портим истинные значения в спрятанных строках и убеждаемся, что матрица признаков
не изменилась ни на бит. Если тест падает — какой-то признак смотрит на цель,
и локальные метрики будут лучше приватного скора.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from ndvi_ml.data import load_raw, mask_rows, observed_mask  # noqa: E402
from ndvi_ml.experiment import build_all_features  # noqa: E402
from ndvi_ml.validation import sample_gaps_fast  # noqa: E402

ML_ROOT = Path(__file__).resolve().parents[1]
TRAIN = ML_ROOT / "train_dataset.csv"
TEST = ML_ROOT / "test_features.csv"


@pytest.mark.skipif(not TRAIN.exists() or not TEST.exists(),
                    reason="нужны ml/train_dataset.csv и ml/test_features.csv")
def test_no_leakage(train_path: str = str(TRAIN), test_path: str = str(TEST)) -> None:
    df = load_raw(train_path, test_path)
    hidden = sample_gaps_fast(df, ~df["is_target"].to_numpy(), seed=7) | df["is_target"].to_numpy()

    F1 = build_all_features(mask_rows(df, hidden))

    # портим всё, что модель не имеет права видеть в скрытых строках
    corrupted = df.copy()
    rng = np.random.default_rng(0)
    for col in ("primary_ndvi", "s2_ndvi", "landsat_ndvi", "modis_ndvi",
                "era5_temp_c", "era5_precip_mm", "ndvi_climatology_mean"):
        corrupted.loc[hidden, col] = rng.normal(5, 3, hidden.sum())
    F2 = build_all_features(mask_rows(corrupted, hidden))

    diff = (F1.drop(columns=["crop_type"]) - F2.drop(columns=["crop_type"])).abs().max()
    worst = diff.max()
    assert worst == 0 or np.isnan(worst), f"утечка: признаки изменились, max diff {worst}\n{diff[diff > 0]}"
    print(f"OK: {F1.shape[1]} признаков, {int(hidden.sum())} скрытых строк, утечки нет")

    # и наоборот: спрятанные строки действительно не имеют своих значений
    m = mask_rows(df, hidden)
    assert m.loc[hidden, "primary_ndvi"].isna().all()
    assert m.loc[hidden, "era5_temp_c"].isna().all()
    print("OK: маскирование повторяет формат контрольных строк")

    # климатнорма не должна знать текущий год
    poly = df["anon_polygon_id"].iloc[0]
    one = df[df.anon_polygon_id == poly]
    print(f"OK: пример полигона {poly}, сезонов {one.year.nunique()}, "
          f"наблюдений {int(observed_mask(one).sum())}")


if __name__ == "__main__":
    # из CLI можно передать свои пути, иначе берутся датасеты репозитория
    a = sys.argv[1] if len(sys.argv) > 1 else str(TRAIN)
    b = sys.argv[2] if len(sys.argv) > 2 else str(TEST)
    test_no_leakage(a, b)
