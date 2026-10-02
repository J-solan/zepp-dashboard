"""Tests de ``backend.api`` sobre una DB temporal poblada con el pipeline de ``ingest.run``.

Reusa el ``FakeClient``/fixtures de ``ingest.tests.test_run`` (mismos payloads
sanitizados) en vez de duplicar datos de ejemplo: así la DB que ve la API
tiene exactamente la forma que produce una ingesta real.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ingest import db, hevy, run
from ingest.tests.test_hevy import base_row, write_csv
from ingest.tests.test_run import CONFIG, FIXTURE_DAY, FakeClient

from backend.api import _day_range_ts, create_app, get_conn

TZ = CONFIG["tz"]


def _seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "zepp.db"
    db.init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    finally:
        conn.close()
    return db_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return _seeded_db(tmp_path)


@pytest.fixture
def client(db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, tz=TZ)
    return TestClient(app)


def _range_params(day: date = FIXTURE_DAY) -> dict:
    return {"from": day.isoformat(), "to": day.isoformat()}


# Los workouts de sport_history.json traen sus propios trackid (unix ts) fijos,
# independientes de FIXTURE_DAY: caen todos entre estas fechas (las fija ``ingest/tests/sanitize_fixtures.py``).
WORKOUTS_RANGE = {"from": "2006-06-01", "to": "2006-07-31"}


# ---------------------------------------------------------------------------
# Helpers de fecha
# ---------------------------------------------------------------------------


def test_day_range_ts_single_day_is_a_full_inclusive_day():
    """from==to (un solo día) no debe colapsar a un rango vacío."""
    start_ts, end_ts = _day_range_ts(FIXTURE_DAY, FIXTURE_DAY, TZ)
    assert end_ts > start_ts
    assert end_ts - start_ts == 86400  # FIXTURE_DAY no es día de cambio de DST

    zone = ZoneInfo(TZ)
    local_start = datetime.fromtimestamp(start_ts, zone)
    local_end = datetime.fromtimestamp(end_ts, zone)
    assert local_start.date() == FIXTURE_DAY
    assert local_start.time() == dt_time(0, 0)
    assert local_end.date() == FIXTURE_DAY + timedelta(days=1)


# ---------------------------------------------------------------------------
# /api/overview
# ---------------------------------------------------------------------------


def test_overview_returns_the_days_cards(client: TestClient):
    resp = client.get("/api/overview", params={"date": FIXTURE_DAY.isoformat()})
    assert resp.status_code == 200
    body = resp.json()

    assert body["date"] == FIXTURE_DAY.isoformat()
    assert body["biocharge"] is not None
    assert 0 <= body["biocharge"]["total"] <= 100
    assert body["steps"] is not None
    assert body["sleep"]["score"] is not None
    assert body["sleep"]["duration_min"] > 0
    assert body["last_sync"]["status"] == "ok"
    assert body["last_sync"]["ts"] is not None


def test_overview_backfills_biocharge_total_from_earlier_non_null_sample(
    client: TestClient, db_path: Path
):
    """La muestra más reciente del día puede traer `total` NULL
    mientras mental/physical ya están (el servidor los calcula con distinto
    retraso). El total debe recuperarse de la muestra no-nula anterior en vez
    de mostrarse como "sin datos" cuando sí hay dato reciente."""
    start_ts, end_ts = _day_range_ts(FIXTURE_DAY, FIXTURE_DAY, TZ)
    conn = sqlite3.connect(db_path)
    try:
        last_ts = conn.execute(
            "SELECT MAX(ts) FROM biocharge WHERE ts >= ? AND ts < ?", (start_ts, end_ts)
        ).fetchone()[0]
        conn.execute("UPDATE biocharge SET total = NULL WHERE ts = ?", (last_ts,))
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/api/overview", params={"date": FIXTURE_DAY.isoformat()})
    assert resp.status_code == 200
    biocharge = resp.json()["biocharge"]
    assert biocharge["ts"] == last_ts
    assert biocharge["total"] is not None
    assert biocharge["mental"] is not None
    assert biocharge["physical"] is not None


def test_overview_defaults_to_today_in_tz(client: TestClient):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    resp = client.get("/api/overview")
    assert resp.status_code == 200
    assert resp.json()["date"] == datetime.now(ZoneInfo(TZ)).date().isoformat()


def test_overview_empty_day_returns_nulls_not_errors(client: TestClient):
    empty_day = FIXTURE_DAY - timedelta(days=365)
    resp = client.get("/api/overview", params={"date": empty_day.isoformat()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["biocharge"] is None
    assert body["sleep"] is None
    assert body["steps"] is None
    # last_sync es global (no depende del día pedido): sigue reportando ok.
    assert body["last_sync"]["status"] == "ok"


# ---------------------------------------------------------------------------
# Series con huecos: /api/hr, /api/stress, /api/biocharge
# ---------------------------------------------------------------------------


def test_hr_series_is_scoped_to_the_range(client: TestClient):
    resp = client.get("/api/hr", params=_range_params())
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"series", "stats"}
    points = body["series"]
    assert points
    assert all(set(p) == {"ts", "bpm"} for p in points)
    # bpm None = marcador de hueco; el resto, centinelas ya descartados.
    assert all(p["bpm"] is None or 30 <= p["bpm"] <= 220 for p in points)
    assert set(body["stats"]) == {"min", "avg", "max"}


def test_hr_series_outside_range_is_empty(client: TestClient):
    far_day = (FIXTURE_DAY - timedelta(days=365)).isoformat()
    resp = client.get("/api/hr", params={"from": far_day, "to": far_day})
    assert resp.status_code == 200
    body = resp.json()
    assert body["series"] == []
    assert body["stats"] == {"min": None, "avg": None, "max": None}


def test_series_endpoints_reject_inverted_range(client: TestClient):
    params = {"from": FIXTURE_DAY.isoformat(), "to": (FIXTURE_DAY - timedelta(days=1)).isoformat()}
    for path in ("/api/hr", "/api/stress", "/api/biocharge", "/api/sleep", "/api/workouts", "/api/daily"):
        resp = client.get(path, params=params)
        assert resp.status_code == 400, path


def test_stress_series_shape(client: TestClient):
    resp = client.get("/api/stress", params=_range_params())
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"series", "stats"}
    for point in body["series"]:
        assert set(point) == {"ts", "value"}
    assert set(body["stats"]) == {"min", "avg", "max"}


def test_biocharge_series_shape(client: TestClient):
    resp = client.get("/api/biocharge", params=_range_params())
    assert resp.status_code == 200
    points = resp.json()
    assert points
    assert all(set(p) == {"ts", "total", "mental", "physical", "status"} for p in points)


# ---------------------------------------------------------------------------
# /api/daily
# ---------------------------------------------------------------------------


def test_daily_returns_the_days_of_the_range(client: TestClient):
    """El histórico diario que alimenta las mini-tendencias del bloque "Hoy"."""
    day_before = (FIXTURE_DAY - timedelta(days=1)).isoformat()
    resp = client.get("/api/daily", params={"from": day_before, "to": FIXTURE_DAY.isoformat()})
    assert resp.status_code == 200
    rows = resp.json()

    # Solo días CON fila: el día anterior no se ingirió, así que no se inventa.
    assert [r["day"] for r in rows] == [FIXTURE_DAY.isoformat()]
    row = rows[0]
    # Columnas de la tabla wide, aunque el día no las tenga todas rellenas.
    assert {"day", "steps", "readiness", "resting_hr", "hrv_ms", "respiratory_rate", "stress_avg"} <= set(row)
    assert row["steps"] is not None


def test_daily_range_without_data_is_an_empty_list(client: TestClient):
    far_day = (FIXTURE_DAY - timedelta(days=365)).isoformat()
    resp = client.get("/api/daily", params={"from": far_day, "to": far_day})
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# /api/sleep
# ---------------------------------------------------------------------------


def test_sleep_returns_session_with_stages(client: TestClient):
    resp = client.get("/api/sleep", params=_range_params())
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1
    session = sessions[0]
    assert session["day"] == FIXTURE_DAY.isoformat()
    assert session["stages"]
    assert all(s["stage"] in (4, 5, 7, 8) for s in session["stages"])
    total_from_stages = sum(s["end_ts"] - s["start_ts"] for s in session["stages"])
    assert total_from_stages > 0


# ---------------------------------------------------------------------------
# /api/workouts + /api/workouts/pending + revisión
# ---------------------------------------------------------------------------


def test_workouts_carry_effective_sport_and_duration(client: TestClient):
    """Tipo efectivo = lo que dijo el usuario, si no el mapa ``sport_types``."""
    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    by_type = {w["sport_type"]: w for w in workouts}
    assert by_type[52]["effective_sport"] == "fuerza"
    assert by_type[122]["effective_sport"] == "voley_playa"
    assert by_type[777]["effective_sport"] is None  # code fuera del mapa, sin revisar
    assert all(w["duration_s"] == w["end_ts"] - w["start_ts"] for w in workouts)


def test_workouts_excludes_ignored(client: TestClient, db_path: Path):
    conn = sqlite3.connect(db_path)
    workout_id = conn.execute("SELECT id FROM workout LIMIT 1").fetchone()[0]
    conn.execute("UPDATE workout SET review_status = 'ignored' WHERE id = ?", (workout_id,))
    conn.commit()
    conn.close()

    resp = client.get("/api/workouts", params=WORKOUTS_RANGE)
    assert resp.status_code == 200
    assert workout_id not in [w["id"] for w in resp.json()]


def test_workouts_parses_hr_zones_and_includes_hr_overlay(client: TestClient):
    resp = client.get("/api/workouts", params=WORKOUTS_RANGE)
    assert resp.status_code == 200
    workouts = resp.json()
    assert workouts

    with_zones = [w for w in workouts if w["hr_zones"]]
    assert with_zones
    zone = with_zones[0]["hr_zones"][0]
    assert set(zone) == {"seconds", "threshold"}

    assert "hr_overlay" in workouts[0]
    for point in workouts[0]["hr_overlay"]:
        assert workouts[0]["start_ts"] <= point["ts"] <= workouts[0]["end_ts"]


def test_workouts_pending_lists_only_pending_and_no_hr_overlay(client: TestClient):
    resp = client.get("/api/workouts/pending")
    assert resp.status_code == 200
    pending = resp.json()
    assert pending
    assert all(w["review_status"] == "pending" for w in pending)
    assert all("hr_overlay" not in w for w in pending)


def test_review_classify_removes_from_pending_and_survives_reingest(client: TestClient, db_path: Path):
    pending_before = client.get("/api/workouts/pending").json()
    assert pending_before
    workout_id = pending_before[0]["id"]

    resp = client.post(
        f"/api/workouts/{workout_id}/review", json={"action": "classify", "sport": "voley_playa"}
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "classified"
    assert resp.json()["user_sport"] == "voley_playa"

    pending_after = client.get("/api/workouts/pending").json()
    assert workout_id not in [w["id"] for w in pending_after]

    # Re-ingesta (misma DB, mismo fixture): la clasificación manual debe sobrevivir.
    conn = sqlite3.connect(db_path)
    try:
        run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    finally:
        conn.close()

    pending_reingested = client.get("/api/workouts/pending").json()
    assert workout_id not in [w["id"] for w in pending_reingested]
    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    reclassified = next(w for w in workouts if w["id"] == workout_id)
    assert reclassified["review_status"] == "classified"
    assert reclassified["user_sport"] == "voley_playa"


# ---------------------------------------------------------------------------
# PATCH /api/workouts/{id}: edición del usuario
# ---------------------------------------------------------------------------


def _any_workout(client: TestClient) -> dict:
    return client.get("/api/workouts", params=WORKOUTS_RANGE).json()[0]


def _sport_names(client: TestClient) -> list[str]:
    return [s["name"] for s in client.get("/api/sports").json()]


def test_sports_lists_config_names_and_everything_the_user_has_typed(client: TestClient):
    """Escribir una categoría una vez ES crearla: a partir de ahí está
    disponible en el desplegable de todos los entrenos."""
    before = _sport_names(client)
    assert "fuerza" in before and "padel" not in before

    workout = _any_workout(client)
    client.patch(f"/api/workouts/{workout['id']}", json={"user_sport": "padel"})

    after = _sport_names(client)
    assert "padel" in after
    assert after == sorted(set(after))  # ordenado y sin duplicados
    assert all(s["color"] is None for s in client.get("/api/sports").json())


def test_a_label_can_be_created_before_any_workout_uses_it(client: TestClient):
    assert "escalada" not in _sport_names(client)
    assert client.put("/api/sports/escalada", json={"color": "#8b5cf6"}).status_code == 200

    created = next(s for s in client.get("/api/sports").json() if s["name"] == "escalada")
    assert created["color"] == "#8b5cf6"


def test_setting_a_colour_on_a_sport_that_came_from_workouts(client: TestClient):
    client.put("/api/sports/fuerza", json={"color": "#ff0000"})
    assert next(s for s in client.get("/api/sports").json() if s["name"] == "fuerza")["color"] == "#ff0000"
    # Sin duplicar: 'fuerza' viene de los workouts Y de sport_style.
    assert _sport_names(client).count("fuerza") == 1


def test_deleting_a_label_never_reclassifies_workouts(client: TestClient):
    """Borrar la etiqueta quita el color, no el dato: si algún entreno la usa,
    la categoría sigue existiendo por uso."""
    workout = _any_workout(client)
    client.patch(f"/api/workouts/{workout['id']}", json={"user_sport": "padel"})
    client.put("/api/sports/padel", json={"color": "#00ff00"})

    assert client.delete("/api/sports/padel").status_code == 204

    still = next(s for s in client.get("/api/sports").json() if s["name"] == "padel")
    assert still["color"] is None  # sin color, pero sigue estando
    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    assert next(w for w in workouts if w["id"] == workout["id"])["user_sport"] == "padel"


def test_deleting_an_unused_label_removes_it_entirely(client: TestClient):
    client.put("/api/sports/escalada", json={"color": "#8b5cf6"})
    client.delete("/api/sports/escalada")
    assert "escalada" not in _sport_names(client)


def test_a_label_without_a_name_is_rejected(client: TestClient):
    assert client.put("/api/sports/%20%20", json={"color": "#fff"}).status_code == 400


def test_patch_edits_title_and_notes(client: TestClient):
    workout = _any_workout(client)
    resp = client.patch(
        f"/api/workouts/{workout['id']}",
        json={"user_title": "  Bici al trabajo  ", "notes": "Con viento en contra"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_title"] == "Bici al trabajo"  # recortado
    assert body["notes"] == "Con viento en contra"
    assert body["effective_title"] == "Bici al trabajo"


def test_user_title_wins_over_the_source_title(client: TestClient, db_path: Path):
    workout = _any_workout(client)
    conn = sqlite3.connect(db_path)
    try:  # simula el sport_title que puso el usuario en la app de Zepp
        conn.execute("UPDATE workout SET title = 'Bici trabajo' WHERE id = ?", (workout["id"],))
        conn.commit()
    finally:
        conn.close()

    assert _any_workout(client)["effective_title"] == "Bici trabajo"  # sin editar, manda la fuente

    client.patch(f"/api/workouts/{workout['id']}", json={"user_title": "Ida al curro"})
    edited = next(w for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json()
                  if w["id"] == workout["id"])
    assert edited["title"] == "Bici trabajo"      # la fuente se conserva
    assert edited["effective_title"] == "Ida al curro"


def test_edits_survive_a_reingest(client: TestClient, db_path: Path):
    """El invariante que motiva la migración 006: la ingesta hace DO UPDATE
    sobre casi todas las columnas en CADA sync. Si ``user_title``/``notes`` no
    estuvieran fuera de ese UPDATE, la edición desaparecería aquí sin avisar."""
    workout = _any_workout(client)
    client.patch(
        f"/api/workouts/{workout['id']}", json={"user_title": "Mío", "notes": "No me pises"}
    )

    conn = sqlite3.connect(db_path)
    try:
        run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    finally:
        conn.close()

    after = next(w for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json()
                 if w["id"] == workout["id"])
    assert after["user_title"] == "Mío"
    assert after["notes"] == "No me pises"


def test_patch_distinguishes_untouched_from_cleared(client: TestClient):
    workout = _any_workout(client)
    client.patch(f"/api/workouts/{workout['id']}", json={"user_title": "T", "notes": "N"})

    # Campo ausente: no se toca. Campo a null: se borra.
    resp = client.patch(f"/api/workouts/{workout['id']}", json={"notes": None})
    assert resp.json()["user_title"] == "T"
    assert resp.json()["notes"] is None

    # Cadena vacía == borrar (es lo que manda un input de texto vaciado).
    resp = client.patch(f"/api/workouts/{workout['id']}", json={"user_title": "   "})
    assert resp.json()["user_title"] is None


def test_patch_without_fields_is_rejected(client: TestClient):
    workout = _any_workout(client)
    assert client.patch(f"/api/workouts/{workout['id']}", json={}).status_code == 400


def test_patch_unknown_workout_is_404(client: TestClient):
    assert client.patch("/api/workouts/999999", json={"notes": "x"}).status_code == 404


def test_patch_to_fuerza_links_hevy_like_the_review_queue(
    client: TestClient, db_path: Path, tmp_path: Path
):
    """Reclasificar por PATCH es la misma decisión que por la cola: debe mover
    el vínculo con Hevy igual, o el overlay de FC quedaría descolgado."""
    assert _import_hevy(db_path, tmp_path, PENDING_DAY)["linked"] == 0
    target = _pending_on(client, PENDING_DAY)

    assert client.patch(f"/api/workouts/{target['id']}", json={"user_sport": "fuerza"}).status_code == 200
    hevy_workout = next(
        w for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json() if w["source"] == "hevy"
    )
    assert hevy_workout["strap"]["id"] == target["id"]

    # Y al revés: si deja de ser fuerza, el vínculo se suelta.
    client.patch(f"/api/workouts/{target['id']}", json={"user_sport": "otro"})
    hevy_workout = next(
        w for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json() if w["source"] == "hevy"
    )
    assert hevy_workout["strap"] is None


# ---------------------------------------------------------------------------
# Descartar y recuperar
# ---------------------------------------------------------------------------


def test_ignored_are_hidden_but_recoverable(client: TestClient):
    """Descartar OCULTA, no borra: tiene que haber camino de vuelta o la cola
    se convierte en un viaje de ida."""
    target = client.get("/api/workouts/pending").json()[0]
    client.post(f"/api/workouts/{target['id']}/review", json={"action": "ignore"})

    visible = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    assert target["id"] not in [w["id"] for w in visible]

    with_ignored = client.get(
        "/api/workouts", params={**WORKOUTS_RANGE, "include_ignored": "true"}
    ).json()
    assert target["id"] in [w["id"] for w in with_ignored]

    assert client.post(f"/api/workouts/{target['id']}/review", json={"action": "restore"}).status_code == 200
    assert client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    assert target["id"] in [w["id"] for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json()]
    assert target["id"] in [w["id"] for w in client.get("/api/workouts/pending").json()]


def test_ignoring_survives_a_reingest(client: TestClient, db_path: Path):
    target = client.get("/api/workouts/pending").json()[0]
    client.post(f"/api/workouts/{target['id']}/review", json={"action": "ignore"})

    conn = sqlite3.connect(db_path)
    try:
        run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    finally:
        conn.close()

    assert target["id"] not in [
        w["id"] for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    ]


# ---------------------------------------------------------------------------
# Entrenos manuales
# ---------------------------------------------------------------------------

MANUAL = {"start_ts": 1783290600, "end_ts": 1783294200, "user_sport": "escalada",
          "user_title": "Rocódromo", "notes": "Sin reloj"}
MANUAL_RANGE = {"from": "2026-07-06", "to": "2026-07-06"}


def test_manual_workout_is_created_and_listed(client: TestClient):
    resp = client.post("/api/workouts", json=MANUAL)
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "manual"
    assert body["effective_sport"] == "escalada"
    assert body["effective_title"] == "Rocódromo"
    assert body["duration_s"] == 3600
    assert body["auto_recognized"] is False
    # No va a la cola: lo acabas de escribir tú, no hay nada que preguntar.
    assert body["review_status"] == "classified"
    assert body["id"] not in [w["id"] for w in client.get("/api/workouts/pending").json()]

    listed = client.get("/api/workouts", params=MANUAL_RANGE).json()
    assert [w["id"] for w in listed] == [body["id"]]


def test_manual_workouts_survive_a_reingest(client: TestClient, db_path: Path):
    """source='manual' los deja fuera del UPSERT, que va por (source='zepp',
    external_id). Ningún sync los toca."""
    created = client.post("/api/workouts", json=MANUAL).json()

    conn = sqlite3.connect(db_path)
    try:
        run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    finally:
        conn.close()

    survivor = client.get("/api/workouts", params=MANUAL_RANGE).json()
    assert [w["id"] for w in survivor] == [created["id"]]
    assert survivor[0]["notes"] == "Sin reloj"


def test_several_manual_workouts_coexist(client: TestClient):
    """external_id NULL: en SQLite los NULL son distintos entre sí para UNIQUE,
    así que el segundo manual no choca con el primero."""
    first = client.post("/api/workouts", json=MANUAL).json()
    second = client.post("/api/workouts", json={**MANUAL, "start_ts": MANUAL["start_ts"] + 7200,
                                                "end_ts": MANUAL["end_ts"] + 7200}).json()
    assert first["id"] != second["id"]
    assert len(client.get("/api/workouts", params=MANUAL_RANGE).json()) == 2


def test_manual_workout_with_inverted_times_is_rejected(client: TestClient):
    bad = {**MANUAL, "end_ts": MANUAL["start_ts"] - 1}
    assert client.post("/api/workouts", json=bad).status_code == 400


def test_a_manual_workout_can_be_deleted(client: TestClient):
    created = client.post("/api/workouts", json=MANUAL).json()
    assert client.delete(f"/api/workouts/{created['id']}").status_code == 204
    assert client.get("/api/workouts", params=MANUAL_RANGE).json() == []


def test_a_watch_workout_cannot_be_deleted(client: TestClient):
    """Borrarlo no serviría: el siguiente sync lo devolvería. Para eso está
    descartar, que sí sobrevive."""
    workout = _any_workout(client)
    resp = client.delete(f"/api/workouts/{workout['id']}")
    assert resp.status_code == 409
    assert "descartan" in resp.json()["detail"]
    assert workout["id"] in [w["id"] for w in client.get("/api/workouts", params=WORKOUTS_RANGE).json()]


def test_deleting_an_unknown_workout_is_404(client: TestClient):
    assert client.delete("/api/workouts/999999").status_code == 404


def test_review_ignore(client: TestClient):
    pending = client.get("/api/workouts/pending").json()
    workout_id = pending[0]["id"]

    resp = client.post(f"/api/workouts/{workout_id}/review", json={"action": "ignore"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "ignored"
    assert workout_id not in [w["id"] for w in client.get("/api/workouts/pending").json()]


def test_review_classify_without_sport_is_rejected(client: TestClient):
    pending = client.get("/api/workouts/pending").json()
    workout_id = pending[0]["id"]
    resp = client.post(f"/api/workouts/{workout_id}/review", json={"action": "classify"})
    assert resp.status_code == 400


def test_review_unknown_id_is_404(client: TestClient):
    resp = client.post("/api/workouts/999999/review", json={"action": "ignore"})
    assert resp.status_code == 404


def test_review_invalid_action_is_422(client: TestClient):
    pending = client.get("/api/workouts/pending").json()
    workout_id = pending[0]["id"]
    resp = client.post(f"/api/workouts/{workout_id}/review", json={"action": "delete"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cruce Hevy <-> strap en /api/workouts
# ---------------------------------------------------------------------------

# Días locales de los workouts del fixture de Zepp (ver la tabla de arriba):
# el 24-jun es el type-52 con FC/carga/zonas completas, el 28-jun un 223 pendiente.
STRAP_STRENGTH_DAY = "2006-06-24"
PENDING_DAY = "2006-06-28"

_MONTH_ABBR = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Mapa mínimo propio en vez de muscle_map.toml: el test comprueba el join, no
# la anatomía del fichero del usuario (que él edita a su gusto).
MUSCLE_MAP = {
    "Press de Banca": {"pecho": 1.0, "triceps": 0.5},
    "Sentadilla": {"cuadriceps": 1.0, "gluteo": 0.7},
}


def _hevy_datetime(day: str, hour: int) -> str:
    year, month, dom = day.split("-")
    return f"{int(dom)} {_MONTH_ABBR[int(month) - 1]} {year}, {hour:02d}:00"


def _import_hevy(db_path: Path, tmp_path: Path, day: str, title: str = "Entrenamiento 💪") -> dict:
    """Importa un entreno de Hevy de 5 series ese día local (3 press + 2 sentadilla)."""
    rows = [
        base_row(
            title=title,
            start_time=_hevy_datetime(day, 17),
            end_time=_hevy_datetime(day, 18),
            exercise_title=exercise,
            set_index=str(i),
            set_type="warmup" if i == 0 else "normal",
            weight_kg="60",
            reps="10",
            rpe="8",
        )
        for exercise, n_sets in (("Press de Banca", 3), ("Sentadilla", 2))
        for i in range(n_sets)
    ]
    csv_path = write_csv(tmp_path / f"hevy-{day}.csv", rows)
    conn = sqlite3.connect(db_path)
    try:
        return hevy.import_csv(conn, csv_path, TZ, MUSCLE_MAP)
    finally:
        conn.close()


def _pending_on(client: TestClient, day: str) -> dict:
    return next(
        p
        for p in client.get("/api/workouts/pending").json()
        if datetime.fromtimestamp(p["start_ts"], ZoneInfo(TZ)).date().isoformat() == day
    )


def test_hevy_workout_brings_sets_muscles_and_strap_data(
    client: TestClient, db_path: Path, tmp_path: Path
):
    assert _import_hevy(db_path, tmp_path, STRAP_STRENGTH_DAY)["linked"] == 1

    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    workout = next(w for w in workouts if w["source"] == "hevy")

    assert workout["effective_sport"] == "fuerza"
    assert workout["title"] == "Entrenamiento 💪"

    assert [e["exercise"] for e in workout["exercises"]] == ["Press de Banca", "Sentadilla"]
    press = workout["exercises"][0]
    assert press["muscle_group"] == "pecho"
    assert len(press["sets"]) == 3
    assert press["sets"][0] == {
        "set_index": 0,
        "reps": 10,
        "weight_kg": 60.0,
        "rpe": 8.0,
        "set_type": "warmup",  # el calentamiento se marca, no se descarta
    }

    assert [(m["muscle"], m["intensity"]) for m in workout["muscles"]] == [
        ("cuadriceps", 1.0),
        ("pecho", 1.0),
        ("gluteo", 0.7),
        ("triceps", 0.5),
    ]

    strap = workout["strap"]
    assert (strap["avg_hr"], strap["max_hr"], strap["train_load"], strap["te"]) == (84, 134, 7, 3.6)
    assert strap["hr_zones"] == [
        {"seconds": 4, "threshold": 78},
        {"seconds": 405, "threshold": 106},
        {"seconds": 80, "threshold": 134},
    ]
    # La ventana del entreno es la del reloj, no la tecleada en el CSV.
    assert (workout["start_ts"], workout["end_ts"]) == (strap["start_ts"], strap["end_ts"])
    assert workout["duration_s"] == strap["end_ts"] - strap["start_ts"]


def test_linked_strap_workout_is_absorbed_and_not_listed_twice(
    client: TestClient, db_path: Path, tmp_path: Path
):
    _import_hevy(db_path, tmp_path, STRAP_STRENGTH_DAY)

    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    workout = next(w for w in workouts if w["source"] == "hevy")

    assert workout["strap"]["id"] not in [w["id"] for w in workouts]
    # Solo desaparece el vinculado: el resto del strap se sigue listando.
    assert [w["id"] for w in workouts if w["source"] == "zepp"]


def test_pending_carries_hevy_evidence_of_the_same_local_day(
    client: TestClient, db_path: Path, tmp_path: Path
):
    _import_hevy(db_path, tmp_path, PENDING_DAY, title="Pierna")

    pending = client.get("/api/workouts/pending").json()
    target = next(
        p
        for p in pending
        if datetime.fromtimestamp(p["start_ts"], ZoneInfo(TZ)).date().isoformat() == PENDING_DAY
    )
    assert target["hevy_evidence"] == {
        "id": target["hevy_evidence"]["id"],
        "title": "Pierna",
        "n_sets": 5,
        "duration_s": 3600,
    }
    # Los pendientes de otros días no heredan la evidencia.
    assert all(p["hevy_evidence"] is None for p in pending if p["id"] != target["id"])


def test_classify_as_fuerza_links_the_unlinked_hevy_of_that_day(
    client: TestClient, db_path: Path, tmp_path: Path
):
    assert _import_hevy(db_path, tmp_path, PENDING_DAY)["linked"] == 0  # el 223 aún no es fuerza
    target = _pending_on(client, PENDING_DAY)

    resp = client.post(
        f"/api/workouts/{target['id']}/review", json={"action": "classify", "sport": "fuerza"}
    )
    assert resp.status_code == 200
    assert resp.json()["effective_sport"] == "fuerza"

    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    workout = next(w for w in workouts if w["source"] == "hevy")
    assert workout["strap"]["id"] == target["id"]
    assert (workout["start_ts"], workout["end_ts"]) == (target["start_ts"], target["end_ts"])
    assert target["id"] not in [w["id"] for w in workouts]  # absorbido
    assert all(p["hevy_evidence"] is None for p in client.get("/api/workouts/pending").json())


def test_classify_as_another_sport_does_not_link_hevy(
    client: TestClient, db_path: Path, tmp_path: Path
):
    _import_hevy(db_path, tmp_path, PENDING_DAY)
    target = _pending_on(client, PENDING_DAY)

    client.post(
        f"/api/workouts/{target['id']}/review", json={"action": "classify", "sport": "voley_playa"}
    )

    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    assert next(w for w in workouts if w["source"] == "hevy")["strap"] is None
    assert target["id"] in [w["id"] for w in workouts]


def test_classify_accepts_free_text_sport(client: TestClient):
    """"Otro" es texto libre. `user_sport` es TEXT y el endpoint NO
    valida contra una lista cerrada a propósito — el usuario hace cosas que la
    app no conoce y etiquetarlas todas como "otro" pierde justo el dato útil.
    Clasificarlos automáticamente queda pendiente."""
    target = _pending_on(client, PENDING_DAY)
    resp = client.post(
        f"/api/workouts/{target['id']}/review", json={"action": "classify", "sport": "pádel"}
    )

    assert resp.status_code == 200
    assert resp.json()["user_sport"] == "pádel"
    assert resp.json()["effective_sport"] == "pádel"

    listed = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    assert next(w for w in listed if w["id"] == target["id"])["effective_sport"] == "pádel"
    assert all(p["id"] != target["id"] for p in client.get("/api/workouts/pending").json())


def test_reclassifying_out_of_fuerza_releases_the_link(
    client: TestClient, db_path: Path, tmp_path: Path
):
    """Un overlay de FC colgado de un entreno que el usuario dice que no era
    fuerza engañaría más que la falta de dato."""
    _import_hevy(db_path, tmp_path, PENDING_DAY)
    target = _pending_on(client, PENDING_DAY)
    url = f"/api/workouts/{target['id']}/review"

    client.post(url, json={"action": "classify", "sport": "fuerza"})
    client.post(url, json={"action": "classify", "sport": "otro"})

    workouts = client.get("/api/workouts", params=WORKOUTS_RANGE).json()
    assert next(w for w in workouts if w["source"] == "hevy")["strap"] is None
    assert target["id"] in [w["id"] for w in workouts]


# ---------------------------------------------------------------------------
# Volumen por músculo
# ---------------------------------------------------------------------------

# El entreno de `_import_hevy` son 5 series de 60 kg × 10 (600 de volumen cada
# una), la primera de cada ejercicio marcada 'warmup': cuentan 2 de press y 1 de
# sentadilla. Con MUSCLE_MAP eso da pecho 1200, tríceps 600, cuádriceps 600 y
# glúteo 420.
EXPECTED_VOLUME = {"pecho": 1200.0, "triceps": 600.0, "cuadriceps": 600.0, "gluteo": 420.0}


def _volume(client: TestClient, params: dict = WORKOUTS_RANGE) -> dict:
    return client.get("/api/muscles/volume", params=params).json()


def test_muscle_volume_splits_each_set_by_intensity(
    client: TestClient, db_path: Path, tmp_path: Path
):
    _import_hevy(db_path, tmp_path, STRAP_STRENGTH_DAY)
    body = _volume(client)

    assert {m["muscle"]: m["volume"] for m in body["muscles"]} == EXPECTED_VOLUME
    assert {m["muscle"]: m["sets"] for m in body["muscles"]} == {
        "pecho": 2,
        "triceps": 2,
        "cuadriceps": 1,
        "gluteo": 1,
    }
    assert body["total_volume"] == round(sum(EXPECTED_VOLUME.values()), 1)
    assert [m["muscle"] for m in body["muscles"]][0] == "pecho"  # ordenado por volumen

    pecho = next(m for m in body["muscles"] if m["muscle"] == "pecho")
    assert pecho["top_exercises"] == [{"exercise": "Press de Banca", "volume": 1200.0, "sets": 2}]


def test_muscle_volume_leaves_warmup_out(client: TestClient, db_path: Path, tmp_path: Path):
    """El calentamiento se guarda pero no es carga: marcar una serie más como
    warmup tiene que restar su volumen y su cuenta."""
    _import_hevy(db_path, tmp_path, STRAP_STRENGTH_DAY)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE workout_set SET set_type='warmup' WHERE id = "
            "(SELECT id FROM workout_set WHERE exercise='Press de Banca' AND set_type='normal' LIMIT 1)"
        )
        conn.commit()
    finally:
        conn.close()

    pecho = next(m for m in _volume(client)["muscles"] if m["muscle"] == "pecho")
    assert (pecho["volume"], pecho["sets"]) == (600.0, 1)


def test_muscle_volume_ignores_discarded_workouts(
    client: TestClient, db_path: Path, tmp_path: Path
):
    _import_hevy(db_path, tmp_path, STRAP_STRENGTH_DAY)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE workout SET review_status='ignored' WHERE source='hevy'")
        conn.commit()
    finally:
        conn.close()

    assert _volume(client)["muscles"] == []


def test_muscle_volume_of_a_range_without_strength_is_empty(
    client: TestClient, db_path: Path, tmp_path: Path
):
    _import_hevy(db_path, tmp_path, STRAP_STRENGTH_DAY)
    body = _volume(client, {"from": "2007-01-01", "to": "2007-01-07"})

    assert body["muscles"] == []
    assert body["total_volume"] == 0


# ---------------------------------------------------------------------------
# Auth Bearer opcional
# ---------------------------------------------------------------------------


def test_open_access_when_no_token_configured(client: TestClient):
    resp = client.get("/api/workouts/pending")
    assert resp.status_code == 200


def test_requires_bearer_token_when_configured(db_path: Path):
    app = create_app(db_path=db_path, tz=TZ, api_token="s3cret")
    protected_client = TestClient(app)

    assert protected_client.get("/api/workouts/pending").status_code == 401
    assert (
        protected_client.get(
            "/api/workouts/pending", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    resp = protected_client.get(
        "/api/workouts/pending", headers={"Authorization": "Bearer s3cret"}
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/sync + GET /api/sync/status
# ---------------------------------------------------------------------------


class _GatedFakeClient(FakeClient):
    """FakeClient que bloquea en ``band_data`` hasta que el test suelta la puerta."""

    def __init__(self, gate: threading.Event):
        super().__init__()
        self._gate = gate

    def band_data(self, from_date, to_date):
        self._gate.wait(timeout=5)
        return super().band_data(from_date, to_date)


def _wait_until_status_is_not(client: TestClient, status: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    body = client.get("/api/sync/status").json()
    while body["status"] == status and time.monotonic() < deadline:
        time.sleep(0.02)
        body = client.get("/api/sync/status").json()
    return body


def test_sync_status_starts_idle(client: TestClient):
    assert client.get("/api/sync/status").json()["status"] == "idle"


def test_sync_without_config_returns_503(client: TestClient):
    resp = client.post("/api/sync")
    assert resp.status_code == 503


def test_sync_off_reason_is_the_503_detail(db_path: Path):
    client = TestClient(create_app(db_path=db_path, tz=TZ, sync_off_reason="modo demo"))
    resp = client.post("/api/sync")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "modo demo"


def test_sync_runs_in_background_and_status_reflects_progress(db_path: Path):
    gate = threading.Event()
    app = create_app(
        db_path=db_path,
        tz=TZ,
        sync_config={**CONFIG, "ventana_dias": 1},
        sync_client_factory=lambda cfg: _GatedFakeClient(gate),
    )
    sync_client = TestClient(app)

    post_resp = sync_client.post("/api/sync")
    assert post_resp.status_code == 202
    assert post_resp.json()["status"] == "running"

    # El endpoint ya respondió y el hilo sigue bloqueado en la puerta: la
    # petición POST no lo esperó (no bloqueante).
    assert sync_client.get("/api/sync/status").json()["status"] == "running"

    gate.set()
    final = _wait_until_status_is_not(sync_client, "running")
    assert final["status"] == "ok"
    assert final["stats"]["ok"] > 0
    assert final["finished_at"] is not None


def test_sync_returns_409_while_already_running(db_path: Path):
    gate = threading.Event()
    app = create_app(
        db_path=db_path,
        tz=TZ,
        sync_config={**CONFIG, "ventana_dias": 1},
        sync_client_factory=lambda cfg: _GatedFakeClient(gate),
    )
    sync_client = TestClient(app)

    assert sync_client.post("/api/sync").status_code == 202
    assert sync_client.post("/api/sync").status_code == 409

    gate.set()
    _wait_until_status_is_not(sync_client, "running")


def test_sync_reports_error_status_without_crashing(db_path: Path):
    def _broken_factory(cfg):
        raise RuntimeError("login rechazado")

    app = create_app(
        db_path=db_path,
        tz=TZ,
        sync_config={**CONFIG, "ventana_dias": 1},
        sync_client_factory=_broken_factory,
    )
    sync_client = TestClient(app)

    assert sync_client.post("/api/sync").status_code == 202
    final = _wait_until_status_is_not(sync_client, "running")
    assert final["status"] == "error"
    assert "login rechazado" in final["error"]


# ---------------------------------------------------------------------------
# Anotaciones manuales
# ---------------------------------------------------------------------------


def _day_bounds(day: date = FIXTURE_DAY) -> tuple[int, int]:
    return _day_range_ts(day, day, TZ)


def _create(client: TestClient, start_ts: int, end_ts: int, text: str = "reunión tensa"):
    return client.post(
        "/api/annotations", json={"start_ts": start_ts, "end_ts": end_ts, "text": text}
    )


def test_annotation_roundtrip_create_list_delete(client: TestClient):
    start, end = _day_bounds()

    created = _create(client, start + 3600, start + 7200, "café doble")
    assert created.status_code == 201
    body = created.json()
    assert body["text"] == "café doble"
    assert body["start_ts"] == start + 3600
    assert body["end_ts"] == start + 7200
    assert body["id"] > 0

    listed = client.get("/api/annotations", params=_range_params()).json()
    assert [a["id"] for a in listed] == [body["id"]]

    assert client.delete(f"/api/annotations/{body['id']}").status_code == 204
    assert client.get("/api/annotations", params=_range_params()).json() == []


def test_annotation_that_straddles_midnight_shows_in_both_days(client: TestClient):
    """Un tramo que cruza la medianoche debe salir al mirar CUALQUIERA de los
    dos días: se filtra por solape, no por 'empieza dentro'."""
    start, end = _day_bounds()
    _create(client, end - 1800, end + 1800, "insomnio")

    today = client.get("/api/annotations", params=_range_params()).json()
    tomorrow = client.get(
        "/api/annotations", params=_range_params(FIXTURE_DAY + timedelta(days=1))
    ).json()

    assert len(today) == 1
    assert len(tomorrow) == 1
    assert today[0]["id"] == tomorrow[0]["id"]


def test_annotation_outside_the_range_is_not_listed(client: TestClient):
    start, _ = _day_bounds()
    _create(client, start - 86400, start - 80000, "de anteayer")

    assert client.get("/api/annotations", params=_range_params()).json() == []


def test_annotation_rejects_empty_text(client: TestClient):
    start, _ = _day_bounds()
    assert _create(client, start, start + 60, "   ").status_code == 400


def test_annotation_rejects_inverted_span(client: TestClient):
    start, _ = _day_bounds()
    assert _create(client, start + 7200, start + 3600).status_code == 400


def test_annotation_text_is_trimmed(client: TestClient):
    start, _ = _day_bounds()
    assert _create(client, start, start + 60, "  resaca  ").json()["text"] == "resaca"


def test_deleting_a_missing_annotation_is_404(client: TestClient):
    assert client.delete("/api/annotations/9999").status_code == 404


def test_annotations_survive_a_re_ingest(db_path: Path, client: TestClient):
    """Las anotaciones son lo único que escribe el usuario: un re-sync que
    reescribe todas las series NO puede llevárselas por delante."""
    start, _ = _day_bounds()
    created = _create(client, start + 3600, start + 7200, "no me borres").json()

    conn = sqlite3.connect(db_path)
    try:
        run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG, incremental=False)
    finally:
        conn.close()

    listed = client.get("/api/annotations", params=_range_params()).json()
    assert [a["id"] for a in listed] == [created["id"]]


# ---------------------------------------------------------------------------
# Conexión por petición
# ---------------------------------------------------------------------------


def test_conn_from_get_conn_is_usable_from_another_thread(db_path: Path):
    """Regresión: 500 intermitente en cualquier endpoint.

    FastAPI resuelve la dependencia generadora y el endpoint en dos envíos
    distintos al threadpool, y anyio puede darles workers diferentes. Si la
    conexión se abriera sin ``check_same_thread=False``, usarla desde otro
    hilo lanzaría ProgrammingError. Se reproduce a mano porque por HTTP el
    cruce de hilos es una carrera y no falla de forma fiable.
    """
    app = create_app(db_path=db_path, tz=TZ)
    request = SimpleNamespace(app=app)
    gen = get_conn(request)
    conn = next(gen)

    failure: list[Exception] = []

    def query_from_worker() -> None:
        try:
            conn.execute("SELECT COUNT(*) FROM annotation").fetchall()
        except Exception as exc:  # noqa: BLE001 - se reporta al hilo principal
            failure.append(exc)

    worker = threading.Thread(target=query_from_worker)
    worker.start()
    worker.join()

    # Y el cierre también ocurre en un tercer hilo distinto.
    closer = threading.Thread(target=lambda: gen.close())
    closer.start()
    closer.join()

    assert failure == [], f"la conexión no es utilizable entre hilos: {failure[0]!r}"


def test_concurrent_requests_do_not_500(client: TestClient):
    """Varias peticiones a la vez (el dashboard lanza ~8 al montar) no pueden
    devolver 500 por la conexión compartida entre hilos."""
    results: list[int] = []
    lock = threading.Lock()

    def hit(path: str) -> None:
        status = client.get(path, params=_range_params()).status_code
        with lock:
            results.append(status)

    paths = ["/api/hr", "/api/stress", "/api/biocharge", "/api/sleep", "/api/annotations"] * 4
    threads = [threading.Thread(target=hit, args=(p,)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results and all(s == 200 for s in results), f"respuestas no-200: {sorted(set(results))}"
