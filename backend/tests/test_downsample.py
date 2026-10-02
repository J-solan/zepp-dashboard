"""Tests del downsampling en servidor: parámetro ``bucket`` y
auto-selección por rango en las series ``/api/hr``, ``/api/stress`` y
``/api/biocharge``.

Cubre: la agregación (media por bucket), los bordes del rango (inclusión
``>= from``, exclusión ``< to+1día`` y alineación del bucket), la elección
automática de resolución y el tope duro de puntos: una serie de 30d
≤ 2.500 puntos y < 200 KB.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import _auto_bucket, create_app
from ingest import db

TZ = "Europe/Madrid"


def _seed(tmp_path: Path, hr: list[tuple[int, int]] | None = None) -> Path:
    db_path = tmp_path / "zepp.db"
    db.init_db(db_path)
    if hr:
        conn = sqlite3.connect(db_path)
        conn.executemany("INSERT INTO hr_minute (ts, bpm) VALUES (?,?)", hr)
        conn.commit()
        conn.close()
    return db_path


@pytest.fixture
def client_factory(tmp_path: Path):
    def make(hr: list[tuple[int, int]] | None = None) -> TestClient:
        return TestClient(create_app(db_path=_seed(tmp_path, hr), tz=TZ))

    return make


def _midnight_ts(day: date) -> int:
    from zoneinfo import ZoneInfo

    return int(datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(TZ)).timestamp())


# ---------------------------------------------------------------------------
# Auto-selección de bucket (tope 2.500 puntos)
# ---------------------------------------------------------------------------


def test_auto_bucket_picks_minute_for_a_single_day():
    start = _midnight_ts(date(2026, 7, 24))
    assert _auto_bucket(start, start + 86400) == 60  # 1440 pts <= 2500


def test_auto_bucket_picks_five_min_for_a_week():
    start = _midnight_ts(date(2026, 7, 24))
    assert _auto_bucket(start, start + 7 * 86400) == 300  # 2016 pts


def test_auto_bucket_keeps_thirty_days_under_the_cap():
    start = _midnight_ts(date(2026, 7, 24))
    bucket = _auto_bucket(start, start + 30 * 86400)
    assert 30 * 86400 / bucket <= 2500


# ---------------------------------------------------------------------------
# Agregación: media por bucket
# ---------------------------------------------------------------------------


def test_bucket_averages_samples_within_each_bucket(client_factory):
    day = date(2026, 7, 24)
    base = _midnight_ts(day)
    # Bucket 0 [base, base+300): 60,70,80 -> media 70. Bucket 1: 90,100 -> 95.
    hr = [
        (base + 0, 60), (base + 60, 70), (base + 120, 80),
        (base + 300, 90), (base + 360, 100),
    ]
    client = client_factory(hr)
    resp = client.get("/api/hr", params={"from": day.isoformat(), "to": day.isoformat(), "bucket": 300})
    assert resp.status_code == 200
    assert resp.json()["series"] == [
        {"ts": base, "bpm": 70},
        {"ts": base + 300, "bpm": 95},
    ]


def test_bucket_ts_is_aligned_to_the_bucket_start(client_factory):
    day = date(2026, 7, 24)
    base = _midnight_ts(day)
    # Una muestra a mitad del bucket debe reportarse en el inicio del bucket.
    client = client_factory([(base + 137, 88)])
    resp = client.get("/api/hr", params={"from": day.isoformat(), "to": day.isoformat(), "bucket": 300})
    assert resp.json()["series"] == [{"ts": base, "bpm": 88}]


# ---------------------------------------------------------------------------
# Huecos como null (dos buckets con datos separados por >1 bucket)
# ---------------------------------------------------------------------------


def test_gap_between_buckets_inserts_a_single_null_marker(client_factory):
    """Dos buckets con datos separados por >1 bucket -> un marcador {ts, value:
    None} entre ellos para CORTAR la línea (hueco real, no interpolar)."""
    day = date(2026, 7, 24)
    base = _midnight_ts(day)
    hr = [(base + 0, 60), (base + 900, 90)]  # buckets 0 y 3 (300s); 1 y 2 vacíos
    client = client_factory(hr)
    resp = client.get("/api/hr", params={"from": day.isoformat(), "to": day.isoformat(), "bucket": 300})
    assert resp.json()["series"] == [
        {"ts": base, "bpm": 60},
        {"ts": base + 300, "bpm": None},  # marcador de hueco
        {"ts": base + 900, "bpm": 90},
    ]


def test_adjacent_buckets_have_no_null_marker(client_factory):
    day = date(2026, 7, 24)
    base = _midnight_ts(day)
    hr = [(base + 0, 60), (base + 300, 90)]  # buckets 0 y 1, consecutivos
    client = client_factory(hr)
    resp = client.get("/api/hr", params={"from": day.isoformat(), "to": day.isoformat(), "bucket": 300})
    assert [p["bpm"] for p in resp.json()["series"]] == [60, 90]  # sin None intermedio


# ---------------------------------------------------------------------------
# {series, stats} con stats EXACTOS sobre el crudo
# ---------------------------------------------------------------------------


def test_response_has_series_and_stats_shape(client_factory):
    day = date(2026, 7, 24)
    client = client_factory([(_midnight_ts(day), 70)])
    body = client.get("/api/hr", params={"from": day.isoformat(), "to": day.isoformat()}).json()
    assert set(body) == {"series", "stats"}
    assert set(body["stats"]) == {"min", "avg", "max"}


def test_stats_are_exact_over_raw_not_downsampled(client_factory):
    """El pico de 1 min (188) debe verse en stats.max aunque la serie lo aplane
    en la media de su bucket (un pico de 188 real se mostraba como 168)."""
    day = date(2026, 7, 24)
    base = _midnight_ts(day)
    # 30 muestras en el mismo bucket de 1800s: 29 a 60 bpm + 1 pico de 188.
    hr = [(base + i * 60, 188 if i == 15 else 60) for i in range(30)]
    client = client_factory(hr)
    body = client.get(
        "/api/hr", params={"from": day.isoformat(), "to": day.isoformat(), "bucket": 1800}
    ).json()
    assert body["stats"]["max"] == 188  # exacto del crudo
    assert body["stats"]["min"] == 60
    # la serie SÍ está downsampleada: el pico se promedia dentro del bucket
    assert max(p["bpm"] for p in body["series"] if p["bpm"] is not None) < 188


def test_empty_range_stats_are_null(client_factory):
    client = client_factory([])
    body = client.get("/api/hr", params={"from": "2026-07-24", "to": "2026-07-24"}).json()
    assert body["series"] == []
    assert body["stats"] == {"min": None, "avg": None, "max": None}


# ---------------------------------------------------------------------------
# Bordes del rango: [from 00:00, to+1día 00:00)
# ---------------------------------------------------------------------------


def test_range_edges_include_start_and_exclude_next_day(client_factory):
    day = date(2026, 7, 24)
    start = _midnight_ts(day)
    end = _midnight_ts(day + timedelta(days=1))
    hr = [
        (start - 60, 50),   # día anterior -> fuera
        (start, 60),        # primer instante del día -> dentro
        (end - 60, 70),     # último minuto del día -> dentro
        (end, 80),          # medianoche siguiente -> fuera (exclusivo)
    ]
    client = client_factory(hr)
    resp = client.get("/api/hr", params={"from": day.isoformat(), "to": day.isoformat(), "bucket": 60})
    # start y end-60 distan >1 bucket -> hay un marcador null entre medias;
    # se filtra para comprobar solo qué muestras REALES caen dentro del rango.
    values = [p["bpm"] for p in resp.json()["series"] if p["bpm"] is not None]
    assert values == [60, 70]


def test_empty_range_returns_empty_list(client_factory):
    client = client_factory([])
    resp = client.get("/api/hr", params={"from": "2026-07-24", "to": "2026-07-24"})
    assert resp.status_code == 200
    assert resp.json()["series"] == []


# ---------------------------------------------------------------------------
# Tope duro: 30d <= 2.500 puntos y < 200 KB
# ---------------------------------------------------------------------------


def test_thirty_day_series_stays_under_point_and_byte_caps(client_factory):
    end_day = date(2026, 7, 24)
    start_day = end_day - timedelta(days=29)
    start = _midnight_ts(start_day)
    # 30 días densos: una muestra por minuto (43.200 filas crudas).
    minutes = 30 * 24 * 60
    hr = [(start + i * 60, 60 + (i % 40)) for i in range(minutes)]
    client = client_factory(hr)

    resp = client.get("/api/hr", params={"from": start_day.isoformat(), "to": end_day.isoformat()})
    assert resp.status_code == 200
    points = resp.json()["series"]
    assert len(points) <= 2500, f"{len(points)} puntos > 2500"
    assert len(resp.content) < 200 * 1024, f"{len(resp.content)} bytes >= 200 KB"
    # y sigue siendo una serie útil, no vacía
    assert len(points) > 100
