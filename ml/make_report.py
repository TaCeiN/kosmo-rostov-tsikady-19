#!/usr/bin/env python3
"""Собирает отчёт из свежих CSV и графиков: REPORT.md, report.html и блок в README.

Ничего не считает сам — только читает то, что произвели run_experiment.py,
predict_submission.py и make_charts.py. Поэтому отчёт не может разъехаться
с реальными цифрами: если файла нет, соответствующий раздел просто не появится.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
from pathlib import Path

import pandas as pd

README_START = "<!-- RESULTS:START -->"
README_END = "<!-- RESULTS:END -->"

RU = {  # человекочитаемые заголовки разрезов
    "scenario": "сценарий валидации",
    "crop_type": "культура",
    "gap_bucket": "длина пропуска",
    "phase": "фаза сезона",
    "year": "год",
}


def md_table(df: pd.DataFrame, index_name: str | None = None, floats: int = 4) -> str:
    """DataFrame -> markdown-таблица."""
    d = df.copy()
    if index_name is not None:
        d = d.reset_index().rename(columns={d.index.name or "index": index_name})
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            # проценты не нужны с точностью до четвёртого знака
            d[c] = d[c].round(1 if ("%" in str(c) or "within" in str(c)) else floats)
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    rows = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |"
            for r in d.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def read(path: Path, **kw) -> pd.DataFrame | None:
    return pd.read_csv(path, **kw) if path.exists() else None


def build_markdown(rep: Path, art: Path) -> tuple[str, str]:
    """Возвращает (краткий блок для README, полный текст REPORT.md)."""
    parts_readme, parts_full = [], []

    overall = read(rep / "metrics_overall.csv")
    if overall is not None:
        overall = overall.set_index("method").sort_values("RMSE")
        n = int(overall["n"].iloc[0])
        short = overall[["RMSE", "MAE", "R2", "within_0.05"]].rename(
            columns={"within_0.05": "±0.05, %"})
        best, base = overall.index[0], "linear"
        gain = (1 - overall.loc[best, "RMSE"] / overall.loc[base, "RMSE"]) * 100 \
            if base in overall.index else float("nan")
        parts_readme.append(
            f"Валидация на сценарии «новый полигон» (полигоны целиком вне обучения — "
            f"так устроены 85% контрольных точек), {n} спрятанных точек:\n\n"
            + md_table(short, "метод")
            + (f"\n\nЛучший метод — **{best}**, −{gain:.0f}% RMSE к линейной интерполяции."
               if gain == gain else ""))
        parts_full.append("## Метрики на сценарии «новый полигон»\n\n"
                          + md_table(overall, "метод"))

    pivot = read(rep / "rmse_pivot.csv")
    if pivot is not None:
        parts_full.append("## RMSE: метод × сценарий\n\n"
                          + md_table(pivot.set_index("method"), "метод"))

    gaps = read(rep / "rmse_by_gap_length.csv")
    if gaps is not None:
        parts_readme.append("RMSE по длине пропуска:\n\n"
                            + md_table(gaps.set_index("gap_bucket"), "длина пропуска"))
        parts_full.append("## RMSE по длине пропуска\n\n"
                          + md_table(gaps.set_index("gap_bucket"), "длина пропуска"))

    for key, title in RU.items():
        s = read(rep / f"slice_{key}.csv")
        if s is not None:
            parts_full.append(f"## Разрез: {title}\n\n" + md_table(s.set_index(s.columns[0]), key))

    status = read(rep / "anomaly_status_agreement.csv")
    if status is not None:
        t = md_table(status.set_index("method"), "метод", floats=2)
        parts_readme.append("Задача 2 — класс аномалии по восстановленному значению против "
                            "класса по факту:\n\n" + t)
        parts_full.append("## Задача 2: перенос ошибок восстановления в классы аномалий\n\n" + t)

    imp = read(rep / "feature_importance.csv")
    if imp is not None:
        parts_full.append("## Топ-20 признаков\n\n"
                          + md_table(imp.head(20).set_index("feature"), "признак", floats=2))

    anom = read(art / "anomalies.csv")
    if anom is not None and len(anom):
        by_cause = anom["cause"].value_counts().rename("периодов").to_frame()
        parts_full.append(
            f"## Найденные аномалии\n\nВсего периодов: **{len(anom)}** на "
            f"{anom.anon_polygon_id.nunique()} полигонах, медианная длительность "
            f"{int(anom.days.median())} дн.\n\n" + md_table(by_cause, "причина"))

    worst = read(rep / "worst_cases.csv")
    if worst is not None:
        parts_full.append("## Худшие случаи\n\n" + md_table(worst.head(10)))

    sub = read(art / "submission.csv")
    if sub is not None:
        parts_full.append(
            f"## Сабмит\n\n`submission.csv`: {len(sub)} строк, "
            f"NDVI {sub.primary_ndvi.min():.3f}..{sub.primary_ndvi.max():.3f}, "
            f"среднее {sub.primary_ndvi.mean():.3f}, пропусков "
            f"{int(sub.primary_ndvi.isna().sum())}.")

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Отчёт по кейсу NDVI\n\nСобран автоматически {stamp} из содержимого `reports/` и `artifacts/`.\n"
    return "\n\n".join(parts_readme), header + "\n" + "\n\n".join(parts_full) + "\n"


HTML_CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #F6F5F1; color: #23241F;
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; }
h1 { font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 19px; margin: 40px 0 12px; padding-bottom: 6px;
  border-bottom: 1px solid #DCDAD2; }
.stamp { color: #6E6F68; font-size: 13px; margin-bottom: 8px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0; }
.card { flex: 1 1 150px; background: #fff; border: 1px solid #DCDAD2;
  border-radius: 10px; padding: 14px 16px; }
.card .v { font-size: 24px; font-weight: 600; color: #2F6F4E; }
.card .l { font-size: 12px; color: #6E6F68; margin-top: 2px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; background: #fff; }
th, td { text-align: right; padding: 7px 10px; border-bottom: 1px solid #E7E5DE; }
th:first-child, td:first-child { text-align: left; font-weight: 500; }
th { background: #EFEDE6; font-weight: 600; white-space: nowrap; }
tbody tr:first-child td { background: #F2F7F3; }
img { display: block; width: 100%; border: 1px solid #DCDAD2;
  border-radius: 10px; background: #fff; margin: 8px 0 4px; }
figcaption { font-size: 12.5px; color: #6E6F68; margin-bottom: 22px; }
"""


def html_table(df: pd.DataFrame, index_name: str, floats: int = 4) -> str:
    d = df.copy().reset_index()
    d = d.rename(columns={d.columns[0]: index_name})
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(floats)
    return '<div class="scroll">' + d.to_html(index=False, border=0, na_rep="") + "</div>"


def build_html(rep: Path, art: Path, charts: Path) -> str:
    blocks = []
    overall = read(rep / "metrics_overall.csv")
    cards = ""
    if overall is not None:
        o = overall.set_index("method").sort_values("RMSE")
        best = o.index[0]
        cards = '<div class="cards">' + "".join(
            f'<div class="card"><div class="v">{v}</div><div class="l">{l}</div></div>'
            for v, l in [
                (f'{o.loc[best, "RMSE"]:.4f}', f"RMSE, {best}"),
                (f'{o.loc[best, "MAE"]:.4f}', "MAE"),
                (f'{o.loc[best, "R2"]:.3f}', "R²"),
                (f'{o.loc[best, "within_0.05"]:.0f}%', "точность ±0.05"),
                (f'{int(o["n"].iloc[0])}', "точек в валидации"),
            ]) + "</div>"
        blocks.append("<h2>Метрики на сценарии «новый полигон»</h2>"
                      + html_table(o, "метод"))

    for fname, title, idx in [
        ("rmse_pivot.csv", "RMSE: метод × сценарий", "method"),
        ("rmse_by_gap_length.csv", "RMSE по длине пропуска", "gap_bucket"),
        ("anomaly_status_agreement.csv", "Задача 2: классы аномалий", "method"),
    ]:
        d = read(rep / fname)
        if d is not None:
            blocks.append(f"<h2>{title}</h2>" + html_table(d.set_index(idx), idx))

    for key, title in RU.items():
        d = read(rep / f"slice_{key}.csv")
        if d is not None:
            blocks.append(f"<h2>Разрез: {title}</h2>" + html_table(d.set_index(d.columns[0]), key))

    captions = {
        "01_methods.png": "Сравнение методов восстановления на отложенных полигонах.",
        "02_gap_length.png": "Чем длиннее пропуск, тем больше выигрыш модели.",
        "03_scatter_residuals.png": "Предсказание против факта и распределение остатков.",
        "04_feature_importance.png": "Вклад признаков в gain.",
        "05_series.png": "Примеры восстановленных рядов: наблюдения, норма и найденные аномалии.",
    }
    figs = []
    for name, cap in captions.items():
        p = charts / name
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        figs.append(f'<figure><img src="data:image/png;base64,{b64}" alt="{cap}">'
                    f"<figcaption>{cap}</figcaption></figure>")
    if figs:
        blocks.append("<h2>Графики</h2>" + "".join(figs))

    imp = read(rep / "feature_importance.csv")
    if imp is not None:
        blocks.append("<h2>Топ-20 признаков</h2>"
                      + html_table(imp.head(20).set_index("feature"), "признак", floats=2))

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return (f"<!doctype html><html lang=ru><head><meta charset=utf-8>"
            f'<meta name=viewport content="width=device-width, initial-scale=1">'
            f"<title>Отчёт NDVI</title><style>{HTML_CSS}</style></head><body><main>"
            f"<h1>Восстановление NDVI и детекция аномалий</h1>"
            f'<div class="stamp">Отчёт собран автоматически {stamp}</div>'
            f"{cards}{''.join(blocks)}</main></body></html>")


def patch_readme(readme: Path, block: str) -> bool:
    """Подменяет блок результатов между маркерами, остальное не трогает."""
    if not readme.exists():
        return False
    text = readme.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return False
    head, rest = text.split(README_START, 1)
    _, tail = rest.split(README_END, 1)
    readme.write_text(f"{head}{README_START}\n\n{block}\n\n{README_END}{tail}", encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--artifacts", default="artifacts")
    ap.add_argument("--charts", default="charts")
    ap.add_argument("--readme", default="README.md")
    args = ap.parse_args()

    rep, art, charts = Path(args.reports), Path(args.artifacts), Path(args.charts)
    short, full = build_markdown(rep, art)

    (rep / "REPORT.md").write_text(full, encoding="utf-8")
    html_path = rep / "report.html"
    html_path.write_text(build_html(rep, art, charts), encoding="utf-8")
    print(f"{rep / 'REPORT.md'}\n{html_path} ({html_path.stat().st_size // 1024} КБ)")

    if patch_readme(Path(args.readme), short):
        print(f"{args.readme}: блок результатов обновлён")
    else:
        print(f"{args.readme}: маркеры {README_START} не найдены, README не тронут")


if __name__ == "__main__":
    main()
