"""Смоук-тест HTTP-сервиса: поднимаем приложение и стучимся как веб-интерфейс.

Проверяет ровно те вызовы, которые делает фронтенд, и на настоящих данных:
контракт /predict легко сломать незаметно, а падает он уже в браузере.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "ml"))

MODEL = REPO_ROOT / "ml" / "artifacts" / "ndvi_model.pkl"
SAMPLE = REPO_ROOT / "ml" / "test_features.csv"

pytestmark = pytest.mark.skipif(
    not MODEL.exists() or not SAMPLE.exists(),
    reason="нужны ml/artifacts/ndvi_model.pkl и ml/test_features.csv",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from serve import app
    return TestClient(app)


@pytest.fixture(scope="module")
def rows():
    """Вся история одного полигона: климатнорма строится по всем его сезонам."""
    df = pd.read_csv(SAMPLE)
    one = df[df["anon_polygon_id"] == df["anon_polygon_id"].iloc[0]]
    # через to_json, потому что NaN не сериализуется — фронт делает так же
    return json.loads(one.to_json(orient="records"))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["features"] > 0


def test_meta_has_frontend_contract(client):
    body = client.get("/meta").json()
    for key in ("region_box", "crop_types", "years", "max_area_ha",
                "gee_available", "ai_available"):
        assert key in body, f"/meta потерял поле {key}"
    assert body["years"]["min_span"] >= 3


def test_predict_restores_series_and_finds_anomalies(client, rows):
    r = client.post("/predict", json={"rows": rows})
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["summary"]["rows"] == len(rows)
    assert d["summary"]["observed"] + d["summary"]["reconstructed"] == len(rows)
    assert len(d["series"]) == len(rows)

    # Ряд должен быть заполнен числами во всех точках. Диапазон не проверяем:
    # наблюдения проходят насквозь как есть, а в разметке организаторов есть
    # несколько физически невозможных значений (см. REPORT.md, раздел 6).
    filled = [p["ndvi_filled"] for p in d["series"]]
    assert all(v is not None for v in filled), "в ряду остались пропуски"
    assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in filled)

    # а вот восстановленные моделью значения обязаны лежать в границах clip
    lo, hi = client.get("/health").json()["config"]["clip"]
    recon = [p["ndvi_filled"] for p in d["series"] if p.get("ndvi_obs") is None]
    assert recon, "нет ни одной восстановленной точки"
    assert all(lo - 1e-9 <= v <= hi + 1e-9 for v in recon)

    for a in d["anomalies"]:
        assert a["z_min"] < 0, "аномалия — это отклонение вниз"
        assert a["days"] >= 10, "период короче 10 суток — шум, а не угнетение"


def test_predict_accepts_bare_rows(client, rows):
    """Новый полигон: у интерфейса есть только id, дата и культура."""
    bare = [{k: v for k, v in row.items()
             if k in ("anon_polygon_id", "date", "crop_type")} for row in rows[:400]]
    r = client.post("/predict", json={"rows": bare, "with_anomalies": False})
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["rows"] == len(bare)
