#!/usr/bin/env python3
"""Ищет лучшую смесь уже посчитанных предсказаний — без единого переобучения.

Предсказания каждой конфигурации лежат в night/preds/*.npz, поэтому перебор
ансамблей стоит секунды. Веса ищутся жадно: на каждом шаге добавляется модель,
которая сильнее всего опускает RMSE (модель может входить в смесь несколько раз —
это и даёт ей больший вес).
"""
from __future__ import annotations
import argparse, pickle, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREDS = ROOT / "night" / "preds"


def load(cache: str):
    y, order = [], []
    for p in sorted((ROOT / cache).glob("new_polygon_fold*.pkl")):
        with open(p, "rb") as f:
            y.append(pickle.load(f)["y_ev"].astype(float))
        order.append(p.stem)
    return np.concatenate(y), order


def preds_of(name: str, order: list[str]) -> np.ndarray | None:
    p = PREDS / f"{name}.npz"
    if not p.exists():
        return None
    d = np.load(p)
    if not all(k in d for k in order):
        return None
    return np.concatenate([d[k] for k in order])


def rmse(p, y): return float(np.sqrt(np.mean((p - y) ** 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="cache_v3")
    ap.add_argument("--candidates", default="", help="через запятую; пусто = все")
    ap.add_argument("--steps", type=int, default=8)
    a = ap.parse_args()

    y, order = load(a.cache)
    names = ([n.strip() for n in a.candidates.split(",") if n.strip()]
             or [p.stem for p in sorted(PREDS.glob("*.npz"))])
    pool = {}
    for n in names:
        p = preds_of(n, order)
        if p is not None and len(p) == len(y):
            pool[n] = p
    if not pool:
        print("нет подходящих предсказаний"); return

    solo = sorted(((rmse(p, y), n) for n, p in pool.items()))
    print("одиночные:")
    for r, n in solo[:10]:
        print(f"  {n:<28} {r:.5f}")

    chosen: list[str] = []
    acc = np.zeros_like(y)
    best_r = np.inf
    for _ in range(a.steps):
        cand = min(((rmse((acc * len(chosen) + p) / (len(chosen) + 1), y), n)
                    for n, p in pool.items()), key=lambda t: t[0])
        if cand[0] >= best_r - 1e-6:
            break
        best_r, name = cand
        acc = (acc * len(chosen) + pool[name]) / (len(chosen) + 1)
        chosen.append(name)
        print(f"  + {name:<28} -> {best_r:.5f}")

    if chosen:
        w = {n: chosen.count(n) / len(chosen) for n in dict.fromkeys(chosen)}
        print(f"\nлучшая смесь RMSE={best_r:.5f}, выигрыш к лучшей одиночной "
              f"{solo[0][0] - best_r:+.5f}")
        for n, v in sorted(w.items(), key=lambda t: -t[1]):
            print(f"  {n:<28} вес {v:.2f}")


if __name__ == "__main__":
    main()
