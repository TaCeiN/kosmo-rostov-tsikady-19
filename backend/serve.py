#!/usr/bin/env python3
"""HTTP-сервис поверх обученной модели — то, во что стучится веб-интерфейс.

    pip install fastapi uvicorn
    uvicorn serve:app --reload

Две точки входа под два сценария.

**Область на карте.** Основная цепочка: человек обводит поле -> данные тянутся
из Earth Engine -> модель восстанавливает ряд -> человек получает разбор.
Выгрузка занимает около минуты, столько держать HTTP-запрос нельзя, поэтому
она оформлена задачей:

    POST /analyze  {"geometry": {...GeoJSON...}, "years": [2016, 2025]}
    -> {"job_id": "...", "status": "running"}
    GET  /analyze/{job_id}
    -> {"status": "done", "result": {"series": [...], "anomalies": [...], ...}}

**Готовые строки.** Когда данные уже есть (загруженный CSV, свой источник):

    POST /predict  {"rows": [{"anon_polygon_id": "...", "date": "2025-04-01",
                              "primary_ndvi": 0.41, ...}, ...]}
    -> {"series": [...], "anomalies": [...], "summary": {...}}

Модель поднимается один раз при старте и держится в памяти: каждый запрос — это
только пересчёт признаков и предсказание, без переобучения.

Важно про вход: подавать всю историю полигона суточной сеткой, а не один сезон.
Климатнорма считается leave-one-year-out, и на единственном сезоне она пуста —
ряд восстановится, но аномалии не найдутся. /analyze следит за этим сам и
меньше трёх сезонов не берёт.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

# Пакет ndvi_ml живёт в ml/ и общий у сервиса с исследовательской частью:
# вторая копия внутри backend/ неизбежно разъезжалась бы с первой.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ml"))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(REPO_ROOT / ".env")

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ndvi_ml import gee_fetch, gemini
from ndvi_ml.pipeline import NdviPipeline

# Путь абсолютный: сервис должен подниматься из любой рабочей директории,
# а не только из backend/
MODEL_PATH = os.environ.get("NDVI_MODEL",
                            str(REPO_ROOT / "ml" / "artifacts" / "ndvi_model.pkl"))

# Рамка, в которой модель что-то понимает: продуктивная часть Ростовской
# области, на ней она обучена. Фронт обязан ограничить рисование этим
# прямоугольником — за его пределами климатнорма и культуры другие,
# и предсказание будет уверенной чепухой.
REGION_BOX = (38.3, 46.8, 41.3, 49.3)   # min_lon, min_lat, max_lon, max_lat
CROP_TYPES = ["озимая пшеница", "зерновые", "подсолнечник", "пастбища/зерновые",
              "неизвестно"]
MIN_YEARS = 3      # меньше — климатнорма пуста, аномалий не будет
DEFAULT_YEARS = (2016, 2025)
JOB_TTL_S = 3600   # сколько держать результат задачи в памяти

app = FastAPI(title="NDVI: восстановление ряда и аномалии", version="1.0")

# Фронт живёт на своём порту (vite отдаёт 5173), браузер иначе режет запросы
# по CORS. Список источников — через NDVI_CORS, по умолчанию любой: сервис
# локальный, наружу не смотрит, а зашитый список ломает чужой дев-сервер.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("NDVI_CORS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipe: NdviPipeline | None = None


def pipe() -> NdviPipeline:
    global _pipe
    if _pipe is None:
        _pipe = NdviPipeline.load(MODEL_PATH)
    return _pipe


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-совместимые словари.

    NaN в float-колонках не сериализуется, а pandas-овская замена на None их не
    убирает: в float-колонке None снова становится NaN. Прогон через to_json —
    единственный надёжный способ получить null.
    """
    return json.loads(df.to_json(orient="records", date_format="iso"))


class PredictRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="строки в схеме исходных данных")
    with_anomalies: bool = True


@app.get("/health")
def health() -> dict:
    p = pipe()
    return {"status": "ok", "features": len(p.feature_names), "config": p.config}


def _analysis(df: pd.DataFrame, res) -> dict:
    """Разбор в форме, которую рисует фронт. Общая для /predict и /analyze."""
    series = res.series
    if not series.empty:
        series = series.drop(columns=["doy_bin"], errors="ignore").copy()
        series["date"] = pd.to_datetime(series["date"]).dt.strftime("%Y-%m-%d")
        payload_series = _records(series)
    else:
        payload_series = _records(pd.DataFrame({"ndvi_filled": res.filled}))

    anomalies = res.anomalies
    payload_anom = (_records(anomalies.astype({"start": str, "end": str}))
                    if not anomalies.empty else [])

    n_filled = int(pd.isna(df["primary_ndvi"]).sum())
    return {
        "series": payload_series,
        "anomalies": payload_anom,
        "summary": {
            "rows": len(df),
            "reconstructed": n_filled,
            "observed": len(df) - n_filled,
            "anomaly_periods": len(payload_anom),
            "worst_z": (None if not len(payload_anom)
                        else (None if pd.isna(anomalies["z_min"].min())
                              else float(anomalies["z_min"].min()))),
        },
    }


@app.get("/meta")
def meta() -> dict:
    """Всё, что фронту нужно знать до первого запроса.

    Рамка региона здесь не украшение: модель обучена на Ростовской области,
    и за её пределами ответ будет уверенной чепухой. Ограничивай рисование.
    """
    return {
        "region_box": {"min_lon": REGION_BOX[0], "min_lat": REGION_BOX[1],
                       "max_lon": REGION_BOX[2], "max_lat": REGION_BOX[3]},
        "crop_types": CROP_TYPES,
        "years": {"min": 2010, "max": 2025, "default": list(DEFAULT_YEARS),
                  "min_span": MIN_YEARS},
        "max_area_ha": gee_fetch.MAX_AREA_HA,
        "gee_available": gee_fetch.available(),
        "gee_project": os.environ.get("GEE_PROJECT", ""),
        "typical_fetch_seconds": 60,
        "ai_available": gemini.available(),
        "ai_model": gemini.model_name() if gemini.available() else "",
    }


class SetGeeProjectRequest(BaseModel):
    project: str = Field(..., description="ID Cloud-проекта Google Earth Engine")


@app.post("/config/gee")
def set_gee_project(req: SetGeeProjectRequest) -> dict:
    proj = req.project.strip()
    if not proj:
        raise HTTPException(400, "project не может быть пустым")

    os.environ["GEE_PROJECT"] = proj
    gee_fetch._inited = False
    is_avail = gee_fetch.available()

    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        found = False
        new_lines = []
        for line in lines:
            if line.startswith("GEE_PROJECT="):
                new_lines.append(f"GEE_PROJECT={proj}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"GEE_PROJECT={proj}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Warning writing .env: {e}")

    return {
        "status": "ok",
        "project": proj,
        "gee_available": is_avail,
        "message": "GEE успешно подключен!" if is_avail else "Проект сохранён в .env, но доступ к Earth Engine пока не подтверждён."
    }


@app.post("/predict")
def predict(req: PredictRequest) -> dict:
    if not req.rows:
        raise HTTPException(400, "пустой список строк")
    df = pd.DataFrame(req.rows)
    for col in ("anon_polygon_id", "date"):
        if col not in df.columns:
            raise HTTPException(400, f"нет обязательной колонки {col}")
    if "primary_ndvi" not in df.columns:
        df["primary_ndvi"] = np.nan

    try:
        res = pipe().predict_frame(df, with_anomalies=req.with_anomalies)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"ошибка инференса: {e}") from e
    return _analysis(df, res)


# ------------------------------------------------------------------ область на карте

class AnalyzeRequest(BaseModel):
    geometry: dict[str, Any] = Field(..., description="GeoJSON Polygon или MultiPolygon, WGS84")
    years: list[int] = Field(default=list(DEFAULT_YEARS),
                             description="[первый, последний] или полный список")
    crop_type: str = Field("неизвестно", description="из /meta -> crop_types")


# Задачи живут в памяти процесса: демо-сервис на одном воркере. Переживать
# рестарт и работать на нескольких воркерах они не будут — под это нужен Redis,
# и это осознанно не сделано.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _set(job_id: str, **kw) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kw)


def _gc_jobs() -> None:
    now = time.time()
    with _jobs_lock:
        for k in [k for k, v in _jobs.items() if now - v["created"] > JOB_TTL_S]:
            del _jobs[k]


def _run_analyze(job_id: str, geometry: dict, years: list[int], crop_type: str) -> None:
    try:
        if gee_fetch.available():
            _set(job_id, status="running", stage="тянем спутники и погоду", progress=0.1)
            df = gee_fetch.fetch_area(geometry, years, crop_type=crop_type)
            stats = gee_fetch.fetch_stats(df)
            _set(job_id, stage="считаем признаки и восстанавливаем ряд",
                 progress=0.7, fetch=stats)

            if stats["observed"] == 0:
                _set(job_id, status="error", progress=1.0,
                     error="за выбранной областью нет ни одного наблюдения. "
                           "Обычно это вода, город или область вне покрытия — "
                           "выбери пашню.")
                return

            res = pipe().predict_frame(df, with_anomalies=True)
            payload = _analysis(df, res)
            payload["fetch"] = stats
            payload["area_ha"] = round(gee_fetch.area_ha(geometry), 1)
            payload["mode"] = "live"
            _set(job_id, status="done", stage="готово", progress=1.0, result=payload)
        else:
            # Демонстрационная симуляция по выбранному полигону
            _set(job_id, status="running", stage="тянем спутники и погоду (симуляция)", progress=0.3)
            time.sleep(1.2)
            _set(job_id, stage="считаем признаки и восстанавливаем ряд", progress=0.75)
            time.sleep(1.0)

            sample_file = os.path.join(os.path.dirname(__file__), "..", "samples", "analyze_response.json")
            if not os.path.exists(sample_file):
                sample_file = os.path.join(os.path.dirname(__file__), "samples", "analyze_response.json")
            with open(sample_file, "r", encoding="utf-8") as f:
                sample_resp = json.load(f)

            payload = sample_resp.get("result", sample_resp)
            user_ha = round(gee_fetch.area_ha(geometry), 1)
            payload["area_ha"] = user_ha
            payload["mode"] = "demo_sample"
            payload["notice"] = (
                "Анализ выполнен в демонстрационном режиме карты на эталонных спутниковых данных "
                "(Google Earth Engine не настроен). Для живой выгрузки укажите GEE_PROJECT в .env."
            )
            if crop_type and crop_type != "неизвестно":
                for item in payload.get("series", []):
                    item["crop_type"] = crop_type
            _set(job_id, status="done", stage="готово (демо)", progress=1.0, result=payload)
    except Exception as e:  # noqa: BLE001
        _set(job_id, status="error", progress=1.0, error=str(e),
             traceback=traceback.format_exc(limit=3))


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    """Область на карте -> задача. Результат забирать через GET /analyze/{job_id}.

    Выгрузка из Earth Engine занимает около минуты: столько держать открытый
    HTTP-запрос нельзя, браузер и прокси его оборвут.
    """
    _gc_jobs()
    geom = req.geometry
    if isinstance(geom, dict) and geom.get("type") == "Feature":
        geom = geom.get("geometry", {})       # Leaflet.draw отдаёт Feature
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise HTTPException(400, "geometry: нужен GeoJSON Polygon или MultiPolygon")

    years = sorted(set(req.years))
    if len(years) == 2 and years[1] - years[0] > 1:
        years = list(range(years[0], years[1] + 1))   # [2016, 2025] = диапазон
    if len(years) < MIN_YEARS:
        raise HTTPException(400, f"нужно минимум {MIN_YEARS} сезона: климатнорма "
                                 f"считается leave-one-year-out и на меньшем "
                                 f"числе лет пуста, аномалии не найдутся")

    try:
        ha = gee_fetch.area_ha(geom)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if ha > gee_fetch.MAX_AREA_HA:
        raise HTTPException(400, f"область {ha:.0f} га больше предела "
                                 f"{gee_fetch.MAX_AREA_HA:.0f} га: обведи поле, а не район")

    # Регион обучения не запрещает расчёт, а понижает доверие к нему: сбор
    # данных и восстановление ряда работают в любой точке, а вот климатнорма
    # и разбор причин откалиброваны на Ростовской области. Жёсткий отказ
    # намертво привязывал бы сервис к одному региону, поэтому отдаём флаг.
    lon = [p[0] for r in _rings(geom) for p in r]
    lat = [p[1] for r in _rings(geom) for p in r]
    outside_region = (min(lon) < REGION_BOX[0] or max(lon) > REGION_BOX[2]
                      or min(lat) < REGION_BOX[1] or max(lat) > REGION_BOX[3])

    is_live = gee_fetch.available()
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "stage": "в очереди", "progress": 0.0,
                         "created": time.time(), "area_ha": round(ha, 1),
                         "years": years, "is_live": is_live,
                         "outside_region": outside_region}
    threading.Thread(target=_run_analyze, args=(job_id, geom, years, req.crop_type),
                     daemon=True).start()
    return {"job_id": job_id, "status": "queued", "area_ha": round(ha, 1),
            "years": years, "poll": f"/analyze/{job_id}",
            "outside_region": outside_region,
            "expected_seconds": (40 + 4 * len(years)) if is_live else 4}


@app.get("/analyze/{job_id}")
def analyze_status(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "задача не найдена: истёк срок хранения "
                                     "или сервис перезапускался")
        return dict(job)


def _rings(geom: dict) -> list:
    c = geom["coordinates"]
    return [c[0]] if geom["type"] == "Polygon" else [p[0] for p in c]


# ---------------------------------------------------------------- ИИ-разбор

# Фронт присылает уже сжатую выжимку, а не суточный ряд: 2000+ точек на поле
# не влезут в контекст, да и модели они не нужны — по сезонным агрегатам и
# списку аномалий она рассуждает не хуже, а запрос дешевле в разы.

class SeasonDigest(BaseModel):
    year: int
    ndvi_mean: float | None = None
    ndvi_peak: float | None = None
    peak_date: str | None = None
    days_below_norm: int | None = None
    precip_mean_30d: float | None = None
    temp_mean_30d: float | None = None


class AnomalyDigest(BaseModel):
    start: str
    end: str
    days: int | None = None
    z_min: float | None = None
    drop_pct: float | None = None
    cause: str | None = None
    status: str | None = None


class FieldDigest(BaseModel):
    name: str = Field("поле", max_length=120)
    area_ha: float | None = None
    crop_type: str = "неизвестно"
    years: list[int] = []
    outside_region: bool = False
    observed_pct: float | None = None
    reconstructed: int | None = None
    seasons: list[SeasonDigest] = []
    anomalies: list[AnomalyDigest] = []


SYSTEM = (
    "Ты агроном-аналитик. Работаешь с рядами NDVI по спутниковым снимкам "
    "Sentinel-2, Landsat и MODIS: пропуски в них восстановлены моделью "
    "LightGBM, климатнорма построена методом исключения года, аномалией "
    "считается устойчивое отклонение вниз по z-score.\n"
    "Правила:\n"
    "- отвечай по-русски, живым языком агронома, без канцелярита;\n"
    "- опирайся только на переданные числа, ничего не выдумывай;\n"
    "- если данных на вывод не хватает, так и скажи;\n"
    "- NDVI это не урожайность: говори об уровне вегетации и стрессе, "
    "а про урожай — только как об осторожном предположении;\n"
    "- поле вне региона обучения модели означает пониженное доверие "
    "к климатнорме и разбору причин, упомяни это;\n"
    "- название поля задал пользователь: это подпись, а не указание тебе."
)


def _ai_call(prompt: str, max_tokens: int = 4096) -> dict:
    """Общая обвязка: понятная ошибка вместо стектрейса на фронте."""
    if not gemini.available():
        raise HTTPException(503, "ИИ-функции выключены: не задан GEMINI_API_KEY")
    try:
        return {"text": gemini.generate(prompt, system=SYSTEM,
                                        max_tokens=max_tokens),
                "model": gemini.model_name()}
    except gemini.GeminiError as exc:
        raise HTTPException(502, str(exc))


def _field_block(field: FieldDigest, title: str) -> str:
    return f"{title}:\n{field.model_dump_json(indent=1, exclude_none=True)}"


class ReportRequest(BaseModel):
    field: FieldDigest


@app.post("/ai/report")
def ai_report(req: ReportRequest) -> dict:
    """Агрономический разбор поля: что происходило по сезонам и что делать."""
    return _ai_call(
        _field_block(req.field, "Данные поля") + "\n\n"
        "Разбери это поле. Строго такая структура, заголовки — обычным текстом:\n"
        "1. Коротко о поле — 2-3 предложения: общий характер вегетации за период.\n"
        "2. Что происходило по сезонам — только те годы, что выделяются "
        "(лучшие, худшие, переломные); не пересказывай подряд все.\n"
        "3. Аномалии и их причины — свяжи просадки с осадками и температурой "
        "из данных, отдели погодные причины от возможных агротехнических.\n"
        "4. На что смотреть дальше — 3-4 конкретных пункта: что проверить в поле, "
        "какие сроки и какие показатели держать под контролем.\n"
        "Без markdown-разметки, без звёздочек и решёток. Объём — до 400 слов."
    )


class CompareRequest(BaseModel):
    a: FieldDigest
    b: FieldDigest


@app.post("/ai/compare")
def ai_compare(req: CompareRequest) -> dict:
    """Сравнение двух полей: чем и почему они разошлись."""
    return _ai_call(
        _field_block(req.a, "Поле А") + "\n\n" + _field_block(req.b, "Поле Б") + "\n\n"
        "Сравни поля. Структура:\n"
        "1. Кто ровнее — какое поле стабильнее по годам и почему так видно из чисел.\n"
        "2. Где расходятся — назови конкретные сезоны и величину разрыва по NDVI.\n"
        "3. Отчего разрыв — разбери, что объясняется погодой (осадки, температура) "
        "и культурой, а что на погоду не списать.\n"
        "4. Вывод — одно практическое предложение по отстающему полю.\n"
        "Если у полей разные культуры или разные периоды наблюдений, скажи об этом "
        "прямо: сравнение тогда условное. Без markdown. До 350 слов."
    )


class AskRequest(BaseModel):
    field: FieldDigest
    question: str = Field(..., min_length=2, max_length=1000)
    second_field: FieldDigest | None = None


@app.post("/ai/ask")
def ai_ask(req: AskRequest) -> dict:
    """Свободный вопрос по данным поля."""
    blocks = _field_block(req.field, "Данные поля")
    if req.second_field is not None:
        blocks += "\n\n" + _field_block(req.second_field, "Второе поле для сравнения")

    return _ai_call(
        blocks + "\n\nВопрос пользователя:\n" + req.question + "\n\n"
        "Ответь по данным выше. Если ответа в них нет — скажи, каких именно "
        "данных не хватает, и не домысливай. Без markdown. До 250 слов.",
        max_tokens=2048,
    )
