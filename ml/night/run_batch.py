#!/usr/bin/env python3
"""Прогоняет пачку конфигураций из файла и копит результаты. Устойчив к падениям."""
from __future__ import annotations
import argparse, importlib.util, sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from night.lab import append_result, leaderboard, load_folds, run_config


def load_configs(path: str):
    spec = importlib.util.spec_from_file_location("batch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CONFIGS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--only-folds", default="", help="через запятую, напр. new_polygon_fold0,new_polygon_fold1")
    a = ap.parse_args()
    seeds = tuple(int(s) for s in a.seeds.split(","))

    only = [f.strip() for f in a.only_folds.split(",") if f.strip()] or None
    folds = load_folds(only)
    print(f"фолдов в кэше: {len(folds)}", flush=True)
    for cfg in load_configs(a.batch):
        try:
            row = run_config(cfg, folds, seeds=seeds)
            append_result(row)
            print(f"{row['name']:<28} RMSE={row['RMSE']:.5f} clean={row['RMSE_clean']:.5f} "
                  f"MAE={row['MAE']:.5f} ±0.05={row['within_0.05']:.1f}% {row['secs']}s", flush=True)
        except Exception:
            print(f"!! {cfg['name']} упал:\n{traceback.format_exc()}", flush=True)
    print("\n=== лидерборд ===")
    lb = leaderboard()
    if not lb.empty:
        print(lb[["name", "RMSE", "RMSE_clean", "MAE", "within_0.05", "secs"]].to_string(index=False))


if __name__ == "__main__":
    main()
