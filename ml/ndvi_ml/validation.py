"""Валидация: свои synthetic gaps + честные схемы разбиения.

Организаторы прячут ~15% наблюдений и оценивают только их, причём 85% контрольных
точек приходится на полигоны, которых нет в train. Поэтому основной сценарий —
«новый полигон», а не случайный сплит.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import observed_mask

GAP_RATE = 0.15  # доля наблюдений, спрятанная организаторами: 3112 / (3112 + 17641)


@dataclass
class Scenario:
    """Один сценарий валидации: что прячем и на чём обучаемся."""
    name: str
    hidden: np.ndarray      # строки, замаскированные для построения признаков
    eval_rows: np.ndarray   # строки, по которым считаем метрики
    train_rows: np.ndarray  # строки, на которых учится модель


def sample_gaps_fast(df: pd.DataFrame, rows: np.ndarray, rate: float = GAP_RATE,
                     seed: int = 0) -> np.ndarray:
    """Прячет ~rate наблюдений сериями по 1-4 подряд.

    Облачность выбивает наблюдения пачками, одиночные дырки заметно легче реальных.
    """
    rng = np.random.default_rng(seed)
    obs_idx = np.flatnonzero(rows & observed_mask(df))
    if len(obs_idx) == 0:
        return np.zeros(len(df), dtype=bool)
    poly = df["anon_polygon_id"].to_numpy()[obs_idx]
    n_target = int(len(obs_idx) * rate)
    taken = np.zeros(len(obs_idx), dtype=bool)
    starts = rng.permutation(len(obs_idx))
    cnt = 0
    for s in starts:
        if cnt >= n_target:
            break
        if taken[s]:
            continue
        length = int(rng.integers(1, 5))
        for k in range(length):
            j = s + k
            if j >= len(obs_idx) or taken[j] or poly[j] != poly[s] or cnt >= n_target:
                break
            taken[j] = True
            cnt += 1
    hidden = np.zeros(len(df), dtype=bool)
    hidden[obs_idx[taken]] = True
    return hidden


def scenario_new_polygon(df: pd.DataFrame, n_folds: int = 4, seed: int = 0) -> list[Scenario]:
    """GroupKFold по полигонам: валидационные поля целиком вне обучения.

    Это главный сценарий — 2648 из 3112 контрольных точек на новых полигонах.
    """
    rng = np.random.default_rng(seed)
    # дособранные полигоны в валидацию не попадают: мерить надо на данных
    # организаторов, иначе числа несравнимы с платформой
    own = df["source"].ne("external") if "source" in df else pd.Series(True, index=df.index)
    polys = df.loc[~df["is_target"] & own, "anon_polygon_id"].unique()
    polys = rng.permutation(polys)
    folds = np.array_split(polys, n_folds)
    out = []
    for i, val_polys in enumerate(folds):
        val_rows = df["anon_polygon_id"].isin(val_polys).to_numpy() & ~df["is_target"].to_numpy()
        hidden = sample_gaps_fast(df, val_rows, seed=seed + i)
        train_rows = (~df["anon_polygon_id"].isin(val_polys).to_numpy()
                      & ~df["is_target"].to_numpy()
                      & observed_mask(df))
        out.append(Scenario(f"new_polygon_fold{i}", hidden, hidden.copy(), train_rows))
    return out


def scenario_last_season(df: pd.DataFrame, seed: int = 0) -> Scenario:
    """Знакомый полигон, новый сезон: прячем часть наблюдений последнего года.

    Имитирует 464 контрольные точки на полях из train (все они в сезоне 2025).
    """
    last = df.groupby("anon_polygon_id")["year"].transform("max")
    own = (df["source"].ne("external") if "source" in df
           else pd.Series(True, index=df.index)).to_numpy()
    val_rows = (df["year"] == last).to_numpy() & ~df["is_target"].to_numpy() & own
    hidden = sample_gaps_fast(df, val_rows, seed=seed + 100)
    train_rows = ~hidden & ~df["is_target"].to_numpy() & observed_mask(df)
    return Scenario("last_season", hidden, hidden.copy(), train_rows)


def scenario_random(df: pd.DataFrame, seed: int = 0) -> Scenario:
    """Случайный сплит — оптимистичная оценка, нужна только для сравнения."""
    own = (df["source"].ne("external") if "source" in df
           else pd.Series(True, index=df.index)).to_numpy()
    # прячем только свои строки, а учимся на всех непрятанных, включая дособранные
    hidden = sample_gaps_fast(df, ~df["is_target"].to_numpy() & own, seed=seed + 200)
    train_rows = ~hidden & ~df["is_target"].to_numpy() & observed_mask(df)
    return Scenario("random", hidden, hidden.copy(), train_rows)
