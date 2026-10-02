"""La BBDD de demo: forma, huecos, cola de revisión, Hevy y que la API la sirva entera."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from demo import seed
import demo.__main__ as demo_main
from ingest import db

TZ = "Europe/Madrid"
# El rango cruza el cambio de hora del 25-oct-2026: un día de 25 h no debe
# duplicar ni perder minutos (ts es PRIMARY KEY: un duplicado reventaría).
TODAY = date(2026, 11, 15)
UNTIL = int(datetime(2026, 11, 15, 12, 0, tzinfo=ZoneInfo(TZ)).timestamp())


def _build(path: Path) -> Path:
    seed.build(path, TODAY, until=UNTIL, tz=TZ)
    return path


def _days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory) -> Path:
    return _build(tmp_path_factory.mktemp("demo") / "demo.db")


@pytest.fixture
def conn(demo_db: Path):
    c = sqlite3.connect(demo_db)
    yield c
    c.close()


def _one(conn: sqlite3.Connection, sql: str, *params):
    return conn.execute(sql, params).fetchone()[0]


def test_covers_ninety_days_ending_today(conn):
    assert _one(conn, "SELECT COUNT(DISTINCT day) FROM sync_state") == seed.DAYS
    assert _one(conn, "SELECT MAX(day) FROM sync_state") == TODAY.isoformat()
    assert _one(conn, "SELECT MIN(day) FROM sync_state") == _days_ago(seed.DAYS - 1)


def test_nothing_after_until(conn):
    """Lo posterior a "ahora" no existe: como una pulsera sin sincronizar."""
    assert _one(conn, "SELECT MAX(ts) FROM hr_minute") < UNTIL
    assert _one(conn, "SELECT MAX(ts) FROM biocharge") < UNTIL
    assert _one(conn, "SELECT COUNT(*) FROM workout WHERE end_ts > ?", UNTIL) == 0


def test_gaps_are_real_gaps_but_never_in_the_last_week(conn):
    all_days = {_days_ago(i) for i in range(seed.DAYS)}
    last_week = {_days_ago(i) for i in range(7)}
    without_metrics = all_days - {r[0] for r in conn.execute("SELECT day FROM daily_metrics")}
    without_sleep = all_days - {r[0] for r in conn.execute("SELECT day FROM sleep_session")}
    assert len(without_metrics) == 5  # días sin pulsera
    assert len(without_sleep) == 9  # esos 5 + 4 noches con la pulsera cargando
    assert not (without_metrics | without_sleep) & last_week


def test_bad_week_is_visibly_worse(conn):
    avg = lambda where, *p: _one(conn, f"SELECT AVG(readiness) FROM daily_metrics WHERE {where}", *p)
    bad = avg("day BETWEEN ? AND ?", _days_ago(20), _days_ago(14))
    rest = avg("day NOT BETWEEN ? AND ?", _days_ago(20), _days_ago(14))
    assert bad < rest - 10


def test_review_queue_has_something_to_review(conn):
    pending = conn.execute("SELECT sport, sport_type FROM workout WHERE review_status = 'pending'").fetchall()
    assert 5 <= len(pending) <= 6
    assert (None, seed.UNKNOWN_CODE) in pending  # code que el config no conoce


def test_strength_goes_through_the_real_hevy_importer(conn):
    linked = _one(conn, "SELECT COUNT(*) FROM workout WHERE source='hevy' AND linked_workout_id IS NOT NULL")
    unlinked = _one(conn, "SELECT COUNT(*) FROM workout WHERE source='hevy' AND linked_workout_id IS NULL")
    assert linked > 10
    assert unlinked == 1  # el día de fuerza que el reloj no reconoció
    # Todo ejercicio de las rutinas existe en muscle_map.toml.
    assert _one(conn, "SELECT COUNT(*) FROM workout_set WHERE muscle_group IS NULL") == 0
    assert _one(conn, "SELECT COUNT(*) FROM workout_set WHERE set_type = 'warmup'") > 0


def test_same_today_same_data(demo_db: Path, tmp_path: Path):
    def fingerprint(path: Path) -> dict:
        c = sqlite3.connect(path)
        try:
            return {
                table: c.execute(f"SELECT COUNT(*), TOTAL({col}) FROM {table}").fetchone()
                for table, col in [
                    ("hr_minute", "bpm"),
                    ("stress_sample", "value"),
                    ("biocharge", "total"),
                    ("sleep_stage", "stage"),
                    ("workout", "train_load"),
                    ("workout_set", "weight_kg"),
                    ("daily_metrics", "steps"),
                ]
            }
        finally:
            c.close()

    assert fingerprint(demo_db) == fingerprint(_build(tmp_path / "again.db"))


def test_api_serves_every_view(demo_db: Path):
    client = TestClient(create_app(db_path=demo_db, tz=TZ))
    week = {"from": _days_ago(6), "to": TODAY.isoformat()}
    everything = {"from": _days_ago(seed.DAYS - 1), "to": TODAY.isoformat()}

    def get(path: str, params: dict | None = None):
        resp = client.get(path, params=params)
        assert resp.status_code == 200, f"{path}: {resp.status_code}"
        return resp.json()

    overview = get("/api/overview", {"date": TODAY.isoformat()})
    assert overview["sleep"] and overview["biocharge"] and overview["readiness"]
    assert overview["last_sync"]["status"] == "ok"
    assert len(get("/api/daily", week)) == 7
    assert get("/api/hr", week)["series"]
    assert get("/api/stress", week)["series"]
    assert get("/api/biocharge", week)
    assert len(get("/api/sleep", week)) == 7
    assert get("/api/workouts", everything)
    assert get("/api/muscles/volume", everything)["muscles"]
    assert {"fuerza", "voley_playa", "auto_ia"} <= {s["name"] for s in get("/api/sports")}
    assert any(p["hevy_evidence"] for p in get("/api/workouts/pending"))


def test_ensure_db_reuses_todays_db_rebuilds_stale_and_resets(tmp_path: Path, monkeypatch):
    built = []

    def fake_build(path, today, *, until, **_):
        built.append(today)
        db.init_db(path)
        c = sqlite3.connect(path)
        c.execute("INSERT INTO sync_state VALUES ('band_data', ?, ?, 'ok')", (today.isoformat(), until))
        c.commit()
        c.close()

    monkeypatch.setattr(seed, "build", fake_build)
    path = tmp_path / "demo.db"
    tomorrow = TODAY + timedelta(days=1)

    assert demo_main.ensure_db(path, TODAY, until=UNTIL) is True  # no existe
    assert demo_main.ensure_db(path, TODAY, until=UNTIL) is False  # ya es de hoy
    assert demo_main.ensure_db(path, TODAY, until=UNTIL + demo_main.STALE_AFTER_S) is True  # de hoy, pero vieja
    assert demo_main.ensure_db(path, tomorrow, until=UNTIL) is True  # caducada

    c = sqlite3.connect(path)
    c.execute("INSERT INTO annotation (start_ts, end_ts, text, created_at) VALUES (1, 2, 'x', 3)")
    c.commit()
    c.close()
    assert demo_main.ensure_db(path, tomorrow, until=UNTIL, reset=True) is True
    c = sqlite3.connect(path)
    assert c.execute("SELECT COUNT(*) FROM annotation").fetchone()[0] == 0  # --reset borra lo tocado
    c.close()
    assert built == [TODAY, TODAY, tomorrow, tomorrow]


def test_demo_app_never_syncs(demo_db: Path):
    resp = TestClient(demo_main.make_app(demo_db)).post("/api/sync")
    assert resp.status_code == 503
    assert resp.json()["detail"] == demo_main.SYNC_OFF_REASON
