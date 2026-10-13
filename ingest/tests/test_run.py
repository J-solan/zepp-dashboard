"""Tests de ``ingest.run``: orquestación sobre un ZeppClient mockeado.

El fake devuelve los payloads de ``fixtures/`` (sanitizados, versionados) sin
tocar la red. Cubre los invariantes de la ingesta: idempotencia, landing-first
ante parser roto, preservación de la clasificación manual, derivación de FC y
unidades de tiempo.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ingest import db, run

FIXTURES = Path(__file__).parent / "fixtures"
TZ = "Europe/Madrid"
CONFIG = {"tz": TZ, "sport_types": {"52": "fuerza", "122": "voley_playa", "223": "auto_ia"}}

# Día de referencia de las fixtures (band_data_day.json / biocharge_day.json).
FIXTURE_DAY = date(2006, 7, 26)


def _fixture(name: str) -> dict:
    # Red de seguridad por si se clona sin las fixtures sanitizadas.
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"{name} no disponible en fixtures/ — se omite")
    return json.loads(path.read_text())


def respiratory_payload(day: date, rpms: list[int]) -> dict:
    """1 byte/min anclado a medianoche UTC de ``day`` (ver parse_respiratory)."""
    ts_ms = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
    return {
        "items": [
            {
                "timestamp": ts_ms,
                "value": {
                    "measurements": base64.b64encode(bytes(rpms)).decode(),
                    # offset "equivocado" a propósito: es metadato, no debe mover nada
                    "timeZone": [{"period": [0, len(rpms) - 1], "offset": 3600}],
                },
            }
        ]
    }


def readiness_payload(day: date, *, rdns: int, hrv: int, rhr: int, **value_extra) -> dict:
    ts_ms, _ = run._day_bounds_ms(day, TZ)
    return {
        "items": [
            {
                "timestamp": ts_ms + 8 * 3600 * 1000,
                "value": {
                    "rdnsScore": rdns,
                    "sleepHRV": hrv,
                    "sleepRHR": rhr,
                    "ahiScore": 100,
                    "timestamp": ts_ms,
                    "timestampUpdate": ts_ms + 8 * 3600 * 1000,
                    **value_extra,
                },
            }
        ]
    }


def all_day_stress_payload(day: date, minute_values: dict[int, int], avg: int | None = None) -> dict:
    """all_day_stress de ``day``: item.timestamp = medianoche UTC; ``data`` =
    string JSON de ``[{time, value}]`` con ``time`` en epoch ms absoluto."""
    ts_ms = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
    data = [{"time": ts_ms + minute * 60000, "value": v} for minute, v in sorted(minute_values.items())]
    item: dict = {"timestamp": ts_ms, "data": json.dumps(data)}
    if avg is not None:
        item["avgStress"] = str(avg)
    return {"items": [item]}


def daily_health_payload(day: date, steps: int, calories: int) -> dict:
    ts_ms = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
    return {
        "items": [
            {
                "timestamp": ts_ms,
                "value": {
                    "timeZone": "1,Asia/Shanghai",
                    "samples": [
                        {
                            "s": 0,
                            "dateString": day.isoformat(),
                            "totalSteps": steps,
                            "totalCalories": calories,
                        }
                    ],
                },
            }
        ]
    }


def band_day_with_odd_stage(date_time: str, odd_stage: list[dict]) -> dict:
    slp = {
        "st": 1700000000, "ed": 1700003000, "ss": 77, "dp": 10, "lt": 20, "wc": 1, "rhr": 50,
        "stage": [{"start": 0, "stop": 19, "mode": 4}], "odd_stage": odd_stage,
    }
    return {
        "date_time": date_time,
        "data_hr": base64.b64encode(b"").decode(),
        "summary": base64.b64encode(json.dumps({"slp": slp}).encode()).decode(),
    }


# Valores de pasos/cal del bloque `stp` de la fixture de band_data.
BAND_STEPS, BAND_CALORIES = 8272, 222


class FakeClient:
    """ZeppClient mockeado: devuelve las fixtures y cuenta las llamadas."""

    def __init__(self, band=None, biocharge=None, sport=None, respiratory=None, daily_health=None,
                 sport_load=None, vo2max=None, readiness=None, hrv_rmssd=None, stress=None):
        self._band = _fixture("band_data_day.json") if band is None else band
        self._biocharge = _fixture("biocharge_day.json") if biocharge is None else biocharge
        self._sport = _fixture("sport_history.json") if sport is None else sport
        self._respiratory = (
            respiratory_payload(FIXTURE_DAY, [17, 18, 16, 17]) if respiratory is None else respiratory
        )
        self._daily_health = (
            daily_health_payload(FIXTURE_DAY, 9999, 333) if daily_health is None else daily_health
        )
        self._sport_load = (
            {"items": [{"dayId": FIXTURE_DAY.isoformat(), "currnetDayTrainLoad": 37, "wtlSum": 120}]}
            if sport_load is None
            else sport_load
        )
        self._vo2max = (
            {"items": [{"dayId": FIXTURE_DAY.isoformat(), "vo2max": 47.5}]} if vo2max is None else vo2max
        )
        # Sin datos por defecto: no perturban los tests que no los ejercitan.
        self._readiness = {"items": []} if readiness is None else readiness
        self._hrv_rmssd = {"items": []} if hrv_rmssd is None else hrv_rmssd
        self._stress = {"items": []} if stress is None else stress
        self.calls: list[str] = []
        self.event_windows: dict[tuple[str, str], tuple[int, int]] = {}

    def band_data(self, from_date, to_date):
        self.calls.append("band_data")
        return self._band

    def events(self, event_type, sub_type, from_ms, to_ms, **kwargs):
        self.calls.append(f"events:{event_type}")
        self.event_windows[(event_type, sub_type)] = (from_ms, to_ms)
        return {
            ("Charge", "real_data"): self._biocharge,
            ("RespiratoryRate", "real_data"): self._respiratory,
            ("DailyHealth", "summary"): self._daily_health,
            ("readiness", "watch_score"): self._readiness,
            ("HRVRMSSD", "real_data"): self._hrv_rmssd,
        }[(event_type, sub_type)]

    def events_user(self, event_type, from_ms, to_ms, **kwargs):
        self.calls.append(f"events_user:{event_type}")
        self.event_windows[(event_type, None)] = (from_ms, to_ms)
        return {"all_day_stress": self._stress}[event_type]

    def sport_history(self, **kwargs):
        self.calls.append("sport_history")
        return self._sport

    def sport_load(self, start_day, end_day):
        self.calls.append("sport_load")
        return self._sport_load

    def vo2max(self, start_day, end_day):
        self.calls.append("vo2max")
        return self._vo2max


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "zepp.db"
    db.init_db(db_path)
    connection = sqlite3.connect(db_path)
    yield connection
    connection.close()


def _counts(connection: sqlite3.Connection) -> dict[str, int]:
    return run.table_counts(connection)


# ---------------------------------------------------------------------------
# Idempotencia
# ---------------------------------------------------------------------------


def test_running_twice_leaves_identical_row_counts(conn):
    client = FakeClient()

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)
    first = _counts(conn)
    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)
    second = _counts(conn)

    assert first == second
    # y no está vacío: si no hubiera ingerido nada el test sería trivial
    assert first["hr_minute"] > 0
    assert first["workout"] > 0
    assert first["biocharge"] > 0
    assert first["sleep_session"] == 1
    assert first["sleep_stage"] > 0


def test_parallel_fetch_keeps_idempotency_across_multiple_days(conn):
    """El fetch en paralelo no debe duplicar filas: correr dos
    veces sobre varios días (fetch concurrente real, >workers) deja exactamente
    las mismas cuentas por tabla."""
    days = [FIXTURE_DAY - timedelta(days=i) for i in range(4, -1, -1)]  # 5 días

    run.run_ingest(conn, FakeClient(), days, CONFIG, today=FIXTURE_DAY, incremental=False)
    first = _counts(conn)
    run.run_ingest(conn, FakeClient(), days, CONFIG, today=FIXTURE_DAY, incremental=False)
    second = _counts(conn)

    assert first == second
    assert first["hr_minute"] > 0
    assert first["biocharge"] > 0
    assert first["workout"] > 0


def test_sync_state_is_ok_for_every_source_and_day(conn):
    days = [FIXTURE_DAY - timedelta(days=1), FIXTURE_DAY]

    run.run_ingest(conn, FakeClient(), days, CONFIG)

    rows = conn.execute("SELECT source, day, last_ok_at, status FROM sync_state").fetchall()
    expected_sources = {s for s, *_ in run.PER_DAY_SOURCES} | {s for s, _ in run.WINDOW_SOURCES}
    assert {(s, d) for s, d, _, _ in rows} == {
        (source, day.isoformat()) for source in expected_sources for day in days
    }
    assert all(status == "ok" and last_ok_at for _, _, last_ok_at, status in rows)


def test_window_sources_are_fetched_once_per_run(conn):
    client = FakeClient()

    run.run_ingest(conn, client, [FIXTURE_DAY - timedelta(days=1), FIXTURE_DAY], CONFIG)

    for source in ("sport_history", "sport_load", "vo2max"):
        assert client.calls.count(source) == 1, source
    assert client.calls.count("band_data") == 2
    assert client.calls.count("events:RespiratoryRate") == 2


def test_sport_history_raw_is_one_row_that_does_not_grow_with_each_synced_day(conn):
    """El endpoint devuelve el historial ENTERO: fechar su crudo con el último
    día de la ventana guardaba una copia completa por cada día sincronizado."""
    # Lo que dejaban las versiones anteriores: una fila fechada por sync.
    run.store_raw(conn, "sport_history", "2006-07-20", {"old": 1})
    run.store_raw(conn, "sport_history", "2006-07-21", {"old": 2})

    for day in (FIXTURE_DAY - timedelta(days=1), FIXTURE_DAY, FIXTURE_DAY):
        run.run_ingest(conn, FakeClient(), [day], CONFIG)

    rows = conn.execute("SELECT day, payload FROM raw_ingest WHERE source = 'sport_history'").fetchall()
    assert rows == [("latest", json.dumps(_fixture("sport_history.json"), ensure_ascii=False))]


# ---------------------------------------------------------------------------
# Sync incremental (sin él, una ventana de 30 días tardaba minutos)
# ---------------------------------------------------------------------------


def test_incremental_skips_closed_days_already_ok(conn):
    days = [FIXTURE_DAY - timedelta(days=i) for i in range(4, -1, -1)]
    run.run_ingest(conn, FakeClient(), days, CONFIG, today=FIXTURE_DAY)

    client = FakeClient()
    stats = run.run_ingest(conn, client, days, CONFIG, today=FIXTURE_DAY)

    # safety_days=1 (default): solo los 2 días más recientes se vuelven a pedir.
    assert client.calls.count("band_data") == 2
    assert client.calls.count("events:RespiratoryRate") == 2
    assert stats["skipped"] == 3 * len(run.PER_DAY_SOURCES)
    assert stats["ok"] == 2 * len(run.PER_DAY_SOURCES) + len(run.WINDOW_SOURCES)


def test_incremental_retries_previously_errored_source_day(conn):
    old_day = FIXTURE_DAY - timedelta(days=3)
    corrupt = _fixture("band_data_day.json")
    corrupt["data"][0]["summary"] = base64.b64encode(b"ya-no-soy-json").decode()

    run.run_ingest(conn, FakeClient(band=corrupt), [old_day], CONFIG, today=FIXTURE_DAY)
    assert (
        conn.execute(
            "SELECT status FROM sync_state WHERE source='band_data' AND day=?",
            (old_day.isoformat(),),
        ).fetchone()[0]
        == "error"
    )

    client = FakeClient()
    run.run_ingest(conn, client, [old_day], CONFIG, today=FIXTURE_DAY)

    # se reintenta pese a estar fuera de safety_days, porque no estaba 'ok'
    assert client.calls.count("band_data") == 1
    assert (
        conn.execute(
            "SELECT status FROM sync_state WHERE source='band_data' AND day=?",
            (old_day.isoformat(),),
        ).fetchone()[0]
        == "ok"
    )


@pytest.mark.parametrize(
    "last_ok_offset_s, refetched",
    [
        (-(4 * 3600 + 58 * 60), True),  # pedido a las 19:02 del MISMO día (en curso)
        (-1, True),  # un segundo antes de que cierre day + safety_days
        (0, False),  # a medianoche local de day + safety_days: ya es definitivo
    ],
)
def test_ok_is_only_definitive_if_fetched_after_day_plus_safety_days(conn, last_ok_offset_s, refetched):
    """Un día pedido mientras aún estaba en curso quedó 'ok' con datos
    parciales: al salir de safety_days no debe darse por cerrado para siempre."""
    old_day = FIXTURE_DAY - timedelta(days=3)
    run.run_ingest(conn, FakeClient(), [old_day], CONFIG, today=old_day)
    # safety_days=1 (default): definitivo desde la medianoche local de old_day+1.
    closes_at = run._day_bounds_ms(old_day + timedelta(days=1), TZ)[0] // 1000
    conn.execute("UPDATE sync_state SET last_ok_at = ?", (closes_at + last_ok_offset_s,))
    conn.commit()

    client = FakeClient()
    run.run_ingest(conn, client, [old_day], CONFIG, today=FIXTURE_DAY)

    assert client.calls.count("band_data") == (1 if refetched else 0)


def test_incremental_false_refetches_everything(conn):
    days = [FIXTURE_DAY - timedelta(days=i) for i in range(4, -1, -1)]
    run.run_ingest(conn, FakeClient(), days, CONFIG, today=FIXTURE_DAY)

    client = FakeClient()
    stats = run.run_ingest(conn, client, days, CONFIG, today=FIXTURE_DAY, incremental=False)

    assert client.calls.count("band_data") == len(days)
    assert stats["skipped"] == 0


# Huecos fuera de la ventana: días anteriores a WINDOW_START (ventana de 30).
WINDOW_START = FIXTURE_DAY - timedelta(days=29)


def _before_window(n: int) -> date:
    return WINDOW_START - timedelta(days=n)


def _ingest_ok(conn, days: list[date]) -> None:
    run.run_ingest(conn, FakeClient(), days, CONFIG, today=FIXTURE_DAY, incremental=False)


def test_gap_start_finds_days_that_were_never_requested(conn):
    """Más de ventana_dias entre dos syncs: los días intermedios salieron de
    la ventana sin pedirse nunca."""
    _ingest_ok(conn, [_before_window(6), _before_window(5)])
    _ingest_ok(conn, [_before_window(2), _before_window(1)])

    assert run._first_gap_day(conn, WINDOW_START, TZ, 1) == _before_window(4)


def test_gap_start_counts_errors_and_non_definitive_ok_as_gaps(conn):
    _ingest_ok(conn, [_before_window(n) for n in range(5, 0, -1)])
    assert run._first_gap_day(conn, WINDOW_START, TZ, 1) is None

    run.set_sync_state(conn, "hrv", _before_window(2).isoformat(), "error")
    assert run._first_gap_day(conn, WINDOW_START, TZ, 1) == _before_window(2)

    fetched_same_day = run._day_bounds_ms(_before_window(4), TZ)[0] // 1000 + 19 * 3600
    conn.execute(
        "UPDATE sync_state SET last_ok_at = ? WHERE source = 'band_data' AND day = ?",
        (fetched_same_day, _before_window(4).isoformat()),
    )
    assert run._first_gap_day(conn, WINDOW_START, TZ, 1) == _before_window(4)


def test_gap_start_ignores_window_sources_and_days_inside_the_window(conn):
    assert run._first_gap_day(conn, WINDOW_START, TZ, 1) is None  # sin historial
    # Las fuentes de ventana no son por día: ni abren hueco ni fijan el primer día.
    run.set_sync_state(conn, "vo2max", _before_window(10).isoformat(), "error")
    # Un error DENTRO de la ventana ya lo reintenta el sync normal.
    run.set_sync_state(conn, "band_data", WINDOW_START.isoformat(), "error")

    assert run._first_gap_day(conn, WINDOW_START, TZ, 1) is None


def _patch_main(monkeypatch, tmp_path, *, errors: int = 0) -> dict:
    """``main`` sin red ni config real; captura los días que recibe run_ingest."""
    seen: dict = {}

    def fake_run_ingest(conn, client, days, config, **kwargs):
        seen["days"] = days
        return {"ok": 1, "error": errors, "skipped": 0, "derived_hr": 0}

    monkeypatch.setattr(run, "load_config", lambda: {**CONFIG, "ventana_dias": 30})
    monkeypatch.setattr(run, "init_db", lambda: None)  # ya la crea el fixture conn
    monkeypatch.setattr(run, "DEFAULT_DB_PATH", tmp_path / "zepp.db")
    monkeypatch.setattr(run, "ZeppAuth", lambda config: None)
    monkeypatch.setattr(run, "ZeppClient", lambda auth, config: None)
    monkeypatch.setattr(run, "run_ingest", fake_run_ingest)
    return seen


def test_main_default_mode_extends_the_range_back_to_the_oldest_gap(conn, tmp_path, monkeypatch, capsys):
    seen = _patch_main(monkeypatch, tmp_path)
    today = datetime.now(ZoneInfo(TZ)).date()
    gap = today - timedelta(days=40)
    run.set_sync_state(conn, "band_data", gap.isoformat(), "error")

    run.main([])
    assert (seen["days"][0], seen["days"][-1]) == (gap, today)
    assert f"Recuperando huecos desde {gap.isoformat()}" in capsys.readouterr().out

    # Con rango explícito o --force manda lo que pidió el usuario.
    for argv in (["--days", "3"], ["--force"], ["--from", (today - timedelta(days=3)).isoformat()]):
        run.main(argv)
        assert seen["days"][0] > gap, argv


@pytest.mark.parametrize("errors, exit_code", [(0, 0), (2, 1)])
def test_main_exit_code_signals_sync_errors(conn, tmp_path, monkeypatch, errors, exit_code):
    """Un cron o un timer de systemd solo ve el código de salida."""
    _patch_main(monkeypatch, tmp_path, errors=errors)
    assert run.main([]) == exit_code


def test_steady_state_second_sync_matches_expected_request_count(conn):
    """Blinda el ahorro documentado en IMPROVEMENT_PLAN.md: 213 -> 17 peticiones."""
    days = [FIXTURE_DAY - timedelta(days=i) for i in range(29, -1, -1)]

    first_client = FakeClient()
    run.run_ingest(conn, first_client, days, CONFIG, today=FIXTURE_DAY)
    assert len(first_client.calls) == 213

    second_client = FakeClient()
    run.run_ingest(conn, second_client, days, CONFIG, today=FIXTURE_DAY)
    assert len(second_client.calls) == 17


# ---------------------------------------------------------------------------
# Landing-first: el crudo sobrevive a un parser roto
# ---------------------------------------------------------------------------


def test_broken_payload_keeps_raw_marks_error_and_other_sources_continue(conn):
    corrupt = _fixture("band_data_day.json")
    # 'summary' deja de ser JSON: el parseo del sueño revienta DESPUÉS de que
    # la FC del día ya se haya insertado (ejercita también el rollback).
    corrupt["data"][0]["summary"] = base64.b64encode(b"ya-no-soy-json").decode()
    client = FakeClient(band=corrupt)

    stats = run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert stats["error"] == 1
    # 1. el crudo se guardó igualmente
    raw = conn.execute(
        "SELECT payload FROM raw_ingest WHERE source = 'band_data' AND day = ?",
        (FIXTURE_DAY.isoformat(),),
    ).fetchone()
    assert raw is not None
    assert json.loads(raw[0])["data"][0]["summary"] == corrupt["data"][0]["summary"]

    # 2. sync_state marca error solo en esa fuente
    status = dict(
        conn.execute("SELECT source, status FROM sync_state WHERE day = ?", (FIXTURE_DAY.isoformat(),))
    )
    assert status == {
        "band_data": "error",
        "readiness": "ok",
        "daily_health": "ok",
        "biocharge": "ok",
        "respiratory": "ok",
        "hrv": "ok",
        "all_day_stress": "ok",
        "sport_history": "ok",
        "sport_load": "ok",
        "vo2max": "ok",
    }

    # 3. nada de band_data quedó a medias, y el resto de fuentes SÍ se procesó
    assert conn.execute("SELECT COUNT(*) FROM hr_minute").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sleep_session").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM biocharge").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM workout").fetchone()[0] > 0


def test_fetch_failure_keeps_previous_last_ok_at(conn):
    class Exploding(FakeClient):
        def events(self, *args, **kwargs):
            raise RuntimeError("boom")

    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    before = conn.execute(
        "SELECT last_ok_at FROM sync_state WHERE source = 'biocharge'"
    ).fetchone()[0]

    run.run_ingest(conn, Exploding(), [FIXTURE_DAY], CONFIG)

    after = conn.execute(
        "SELECT last_ok_at, status FROM sync_state WHERE source = 'biocharge'"
    ).fetchone()
    assert after[1] == "error"
    assert after[0] == before  # last_ok_at NO se pisa con un fallo


# ---------------------------------------------------------------------------
# La clasificación manual sobrevive a la re-ingesta
# ---------------------------------------------------------------------------


def test_manual_review_status_and_user_sport_survive_reingest(conn):
    client = FakeClient()
    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    workout_id, external_id = conn.execute(
        "SELECT id, external_id FROM workout WHERE review_status = 'pending' LIMIT 1"
    ).fetchone()
    conn.execute(
        "UPDATE workout SET review_status = 'classified', user_sport = 'voley_playa' WHERE id = ?",
        (workout_id,),
    )
    conn.commit()

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT review_status, user_sport FROM workout WHERE external_id = ?", (external_id,)
    ).fetchone() == ("classified", "voley_playa")


def test_reingest_still_refreshes_metric_columns(conn):
    """Preservar la revisión no debe congelar el resto de la fila."""
    client = FakeClient()
    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)
    external_id = conn.execute("SELECT external_id FROM workout LIMIT 1").fetchone()[0]
    conn.execute("UPDATE workout SET train_load = 999 WHERE external_id = ?", (external_id,))
    conn.commit()

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT train_load FROM workout WHERE external_id = ?", (external_id,)
    ).fetchone()[0] != 999


def test_mapping_a_code_later_moves_its_workouts_from_pending_to_auto(conn):
    """Un usuario nuevo sincroniza ANTES de mapear sus codes: al mapear y
    re-ingerir, lo que solo estaba en la cola por code desconocido sale de ella."""
    sport = _fixture("sport_history.json")
    code = 777  # sesión manual (auto_recognition=false) con code sin mapear
    run.run_ingest(conn, FakeClient(sport=sport), [FIXTURE_DAY], CONFIG)
    assert conn.execute(
        "SELECT review_status FROM workout WHERE sport_type = ?", (code,)
    ).fetchone() == ("pending",)

    mapped = {**CONFIG, "sport_types": {**CONFIG["sport_types"], str(code): "padel"}}
    run.run_ingest(conn, FakeClient(sport=sport), [FIXTURE_DAY], mapped)

    assert conn.execute(
        "SELECT review_status, sport FROM workout WHERE sport_type = ?", (code,)
    ).fetchone() == ("auto", "padel")


def test_reingest_never_overrides_classified_or_ignored(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)
    # Sesiones manuales con code mapeado: la re-ingesta las propone como 'auto'.
    ids = [r[0] for r in conn.execute("SELECT id FROM workout WHERE sport_type = 52 LIMIT 2")]
    conn.execute("UPDATE workout SET review_status = 'classified' WHERE id = ?", (ids[0],))
    conn.execute("UPDATE workout SET review_status = 'ignored' WHERE id = ?", (ids[1],))
    conn.commit()

    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    assert [
        conn.execute("SELECT review_status FROM workout WHERE id = ?", (i,)).fetchone()[0]
        for i in ids
    ] == ["classified", "ignored"]


def test_unknown_sport_code_lands_as_pending_without_sport_name(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    rows = conn.execute(
        "SELECT sport, review_status FROM workout WHERE sport_type NOT IN (52, 122, 223)"
    ).fetchall()
    assert rows
    assert all(sport is None and status == "pending" for sport, status in rows)


# ---------------------------------------------------------------------------
# Derivación de avg_hr/max_hr desde hr_minute
# ---------------------------------------------------------------------------


def _sport_payload_overlapping_hr() -> tuple[dict, int, int]:
    """Fixture de workouts con el primero desplazado sobre el día de FC."""
    payload = _fixture("sport_history.json")
    workout = payload["data"]["summary"][0]
    assert workout["avg_heart_rate"] in ("-1.0", -1.0)  # el que hay que derivar
    # Ventana dentro del día de las fixtures de FC: 08:00-09:00 local.
    start_ms, _ = run._day_bounds_ms(FIXTURE_DAY, TZ)
    start_ts = start_ms // 1000 + 8 * 3600
    end_ts = start_ts + 3600
    workout["trackid"] = str(start_ts)
    workout["end_time"] = str(end_ts)
    return payload, start_ts, end_ts


def test_avg_and_max_hr_are_derived_from_hr_minute(conn):
    payload, start_ts, end_ts = _sport_payload_overlapping_hr()

    stats = run.run_ingest(conn, FakeClient(sport=payload), [FIXTURE_DAY], CONFIG)

    assert stats["derived_hr"] >= 1
    avg_hr, max_hr = conn.execute(
        "SELECT avg_hr, max_hr FROM workout WHERE external_id = ?", (str(start_ts),)
    ).fetchone()
    expected_avg, expected_max = conn.execute(
        "SELECT AVG(bpm), MAX(bpm) FROM hr_minute WHERE ts BETWEEN ? AND ?", (start_ts, end_ts)
    ).fetchone()
    assert avg_hr == round(expected_avg)
    assert max_hr == expected_max


def test_derivation_leaves_workouts_without_hr_samples_null(conn):
    # Los workouts de la fixture caen fuera del día de FC: sin muestras que usar.
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT COUNT(*) FROM workout WHERE avg_hr IS NULL"
    ).fetchone()[0] > 0


def test_derivation_does_not_overwrite_hr_present_in_the_payload(conn):
    payload, start_ts, _ = _sport_payload_overlapping_hr()
    payload["data"]["summary"][0]["avg_heart_rate"] = "111.0"
    payload["data"]["summary"][0]["max_heart_rate"] = 175

    run.run_ingest(conn, FakeClient(sport=payload), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT avg_hr, max_hr FROM workout WHERE external_id = ?", (str(start_ts),)
    ).fetchone() == (111, 175)


@pytest.mark.parametrize("source", ["manual", "hevy"])
def test_derived_hr_follows_hr_that_arrives_after_the_first_derivation(conn, source):
    """Sin FC propia, lo derivado con la ventana a medias (la pulsera aún no
    había subido toda la FC) no puede quedarse congelado."""
    start = 1_784_880_000
    conn.execute(
        "INSERT INTO workout (source, external_id, start_ts, end_ts) VALUES (?, 'x', ?, ?)",
        (source, start, start + 600),
    )
    run._upsert_hr(conn, [(start, 100), (start + 60, 110)])
    run.derive_missing_hr(conn)
    assert conn.execute("SELECT avg_hr, max_hr FROM workout").fetchone() == (105, 110)

    run._upsert_hr(conn, [(start + 120, 150), (start + 180, 160)])
    run.derive_missing_hr(conn)

    assert conn.execute("SELECT avg_hr, max_hr FROM workout").fetchone() == (130, 160)


# ---------------------------------------------------------------------------
# Unidades de tiempo
# ---------------------------------------------------------------------------

TS_COLUMNS = [
    ("hr_minute", "ts"),
    ("biocharge", "ts"),
    ("sleep_session", "start_ts"),
    ("sleep_session", "end_ts"),
    ("sleep_stage", "start_ts"),
    ("sleep_stage", "end_ts"),
    ("workout", "start_ts"),
    ("workout", "end_ts"),
    ("sync_state", "last_ok_at"),
    ("raw_ingest", "fetched_at"),
]


def test_every_stored_timestamp_is_unix_seconds(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    for table, column in TS_COLUMNS:
        rows = conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
        assert rows, f"{table}.{column} sin datos que verificar"
        for (value,) in rows:
            assert 10**9 < value < 10**10, f"{table}.{column}={value} no parece unix s"


def test_daily_metrics_stores_effective_tz(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    assert conn.execute("SELECT tz FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)).fetchone()[0] == TZ
    assert conn.execute("SELECT tz FROM sleep_session").fetchone()[0] == TZ


def test_nap_regrouping_does_not_orphan_the_absorbed_row(conn):
    """Si un re-fetch (hoy/ayer) rellena el hueco entre dos siestas, se
    fusionan en una con el start_ts de la primera: la fila vieja de la
    segunda debe desaparecer, sin dejar sleep_stage huérfano."""
    day = date(2026, 7, 21)
    payload = {"data": [band_day_with_odd_stage(day.isoformat(), [
        {"start": 100, "stop": 110, "mode": 4},
        {"start": 200, "stop": 210, "mode": 4},
    ])]}
    run.process_band_data(conn, payload, day, TZ)
    assert conn.execute("SELECT COUNT(*) FROM sleep_session WHERE is_nap = 1").fetchone()[0] == 2

    payload = {"data": [band_day_with_odd_stage(day.isoformat(), [
        {"start": 100, "stop": 110, "mode": 4},
        {"start": 115, "stop": 195, "mode": 7},
        {"start": 200, "stop": 210, "mode": 4},
    ])]}
    run.process_band_data(conn, payload, day, TZ)

    assert conn.execute("SELECT COUNT(*) FROM sleep_session WHERE is_nap = 1").fetchone()[0] == 1
    orphans = conn.execute(
        "SELECT COUNT(*) FROM sleep_stage WHERE session_id NOT IN (SELECT id FROM sleep_session)"
    ).fetchone()[0]
    assert orphans == 0


# ``slp`` sin noche, tal como llega en algunos band_data: st == ed, sin fases,
# score 0 y rhr 0.
PHANTOM_SLP = {"st": 1700000000, "ed": 1700000000, "ss": 0, "dp": 0, "lt": 0, "wc": 0, "rhr": 0, "stage": []}
NIGHT_SLP = {
    "st": 1700000000, "ed": 1700003000, "ss": 77, "dp": 10, "lt": 20, "wc": 1, "rhr": 50,
    "stage": [{"start": 0, "stop": 19, "mode": 4}],
}


def band_payload_with_slp(date_time: str, slp: dict) -> dict:
    return {"data": [{
        "date_time": date_time,
        "data_hr": base64.b64encode(b"").decode(),
        "summary": base64.b64encode(json.dumps({"slp": slp}).encode()).decode(),
    }]}


def test_phantom_night_stores_no_session_nor_zero_resting_hr_but_keeps_the_naps(conn):
    day = date(2026, 7, 21)
    slp = {**PHANTOM_SLP, "odd_stage": [{"start": 900, "stop": 930, "mode": 4}]}

    run.process_band_data(conn, band_payload_with_slp(day.isoformat(), slp), day, TZ)

    assert conn.execute("SELECT is_nap FROM sleep_session").fetchall() == [(1,)]
    assert conn.execute("SELECT COUNT(*) FROM daily_metrics WHERE resting_hr = 0").fetchone()[0] == 0


def test_a_phantom_refetch_does_not_delete_a_stored_night(conn):
    day = date(2026, 7, 21)
    run.process_band_data(conn, band_payload_with_slp(day.isoformat(), NIGHT_SLP), day, TZ)
    run.process_band_data(conn, band_payload_with_slp(day.isoformat(), PHANTOM_SLP), day, TZ)

    assert conn.execute("SELECT start_ts FROM sleep_session WHERE is_nap = 0").fetchall() == [
        (NIGHT_SLP["st"],)
    ]


def test_refetched_night_with_another_start_does_not_orphan_the_old_one(conn):
    """ON CONFLICT va por (day, start_ts): si un re-fetch trae la noche con otro
    ``st`` (la buena tras una fantasma, o una parcial corregida), la fila vieja
    no la toca nadie y se queda como una segunda noche del mismo día."""
    day = date(2026, 7, 21)
    run.process_band_data(conn, band_payload_with_slp(day.isoformat(), NIGHT_SLP), day, TZ)
    moved = {**NIGHT_SLP, "st": NIGHT_SLP["st"] - 600}
    run.process_band_data(conn, band_payload_with_slp(day.isoformat(), moved), day, TZ)

    assert conn.execute("SELECT start_ts FROM sleep_session WHERE is_nap = 0").fetchall() == [
        (moved["st"],)
    ]
    orphans = conn.execute(
        "SELECT COUNT(*) FROM sleep_stage WHERE session_id NOT IN (SELECT id FROM sleep_session)"
    ).fetchone()[0]
    assert orphans == 0


# ---------------------------------------------------------------------------
# daily_metrics: varias fuentes escribiendo columnas distintas de la misma fila
# ---------------------------------------------------------------------------


def test_daily_health_wins_the_steps_and_calories_conflict(conn):
    """DailyHealth (resumen curado) pisa lo que trae el bloque stp de band_data."""
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT steps, calories FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone() == (9999, 333)


def test_band_data_fills_steps_when_daily_health_has_no_data(conn):
    run.run_ingest(conn, FakeClient(daily_health={"items": []}), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT steps, calories FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone() == (BAND_STEPS, BAND_CALORIES)


def test_sources_writing_the_same_row_do_not_clobber_each_others_columns(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    row = conn.execute(
        "SELECT steps, calories, resting_hr, respiratory_rate, train_load, vo2max, tz "
        "FROM daily_metrics WHERE day = ?",
        (FIXTURE_DAY.isoformat(),),
    ).fetchone()
    assert row == (9999, 333, 59, 17.0, 37, 47.5, TZ)


def test_sport_load_stores_weekly_sum_and_ranges_next_to_the_daily_load(conn):
    item = {
        "dayId": FIXTURE_DAY.isoformat(),
        "currnetDayTrainLoad": 37,
        "wtlSum": 180,
        "wtlSumOptimalMin": 120,
        "wtlSumOptimalMax": 260,
        "wtlSumOverreaching": 330,
    }
    client = FakeClient(sport_load={"items": [item]})

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)
    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT train_load, load_7d, load_7d_optimal_min, load_7d_optimal_max, load_7d_overreaching "
        "FROM daily_metrics WHERE day = ?",
        (FIXTURE_DAY.isoformat(),),
    ).fetchone() == (37, 180, 120, 260, 330)


def test_sport_load_sentinel_range_does_not_clobber_stored_one(conn):
    """Un -1 en un rango es "sin dato" en esa respuesta, no un valor nuevo."""
    day = FIXTURE_DAY.isoformat()
    full = {"dayId": day, "wtlSum": 180, "wtlSumOptimalMin": 120, "wtlSumOptimalMax": 260, "wtlSumOverreaching": 330}
    run.run_ingest(conn, FakeClient(sport_load={"items": [full]}), [FIXTURE_DAY], CONFIG)

    run.run_ingest(conn, FakeClient(sport_load={"items": [{**full, "wtlSumOverreaching": -1}]}), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT load_7d_overreaching FROM daily_metrics WHERE day = ?", (day,)
    ).fetchone()[0] == 330


def test_respiratory_rate_is_the_daily_median(conn):
    client = FakeClient(respiratory=respiratory_payload(FIXTURE_DAY, [0, 14, 16, 18, 20, 0]))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    # centinelas 0 fuera -> mediana de [14,16,18,20] = 17.0
    assert conn.execute(
        "SELECT respiratory_rate FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone()[0] == 17.0


# Zonas lejos de UTC por ambos lados, y la del único usuario real.
FAR_TZS = ["America/Los_Angeles", "Europe/Madrid", "Asia/Tokyo", "Pacific/Auckland"]


def _utc_days_touched(day: date, tz: str) -> list[date]:
    """Días UTC que pisa el día local ``day`` (dos, salvo en UTC)."""
    start_ms, end_ms = run._day_bounds_ms(day, tz)
    first = datetime.fromtimestamp(start_ms / 1000, timezone.utc).date()
    last = datetime.fromtimestamp(end_ms / 1000 - 1, timezone.utc).date()
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


@pytest.mark.parametrize("tz", FAR_TZS)
def test_respiratory_fetch_asks_for_every_utc_item_the_local_day_touches(tz):
    """Un item por día UTC (``timestamp`` = su medianoche UTC): pedir solo el
    día local deja fuera el item donde empieza (o acaba) ese día."""
    client = FakeClient()
    day = date(2026, 7, 21)

    run.fetch_respiratory(client, day, tz)

    from_ms, to_ms = client.event_windows[("RespiratoryRate", "real_data")]
    for utc_day in _utc_days_touched(day, tz):
        assert from_ms <= _utc_midnight_ts(utc_day) * 1000 < to_ms, utc_day


@pytest.mark.parametrize("tz", FAR_TZS)
def test_respiratory_median_lands_on_its_local_day_and_nowhere_else(conn, tz):
    """Cada minuto vale 10/15/20 según caiga en el día local anterior, el
    propio o el siguiente: la mediana del día es 15 y los vecinos no se tocan
    (el fetch de un día no puede pisarlos con una mediana parcial)."""
    day = date(2026, 7, 21)
    zone = ZoneInfo(tz)
    rpm_by_local_day = {day - timedelta(days=1): 10, day: 15, day + timedelta(days=1): 20}
    items = []
    for utc_day in _utc_days_touched(day, tz):
        start = _utc_midnight_ts(utc_day)
        rpms = bytes(
            rpm_by_local_day[datetime.fromtimestamp(start + m * 60, zone).date()] for m in range(1440)
        )
        items.append({"timestamp": start * 1000, "value": {"measurements": base64.b64encode(rpms).decode()}})

    run.process_respiratory(conn, {"items": items}, day, tz)

    assert conn.execute("SELECT day, respiratory_rate FROM daily_metrics").fetchall() == [
        (day.isoformat(), 15.0)
    ]


def test_respiratory_intraday_series_is_not_persisted_but_raw_is_kept(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "respiratory_sample" not in tables
    assert conn.execute(
        "SELECT COUNT(*) FROM raw_ingest WHERE source = 'respiratory'"
    ).fetchone()[0] == 1


def test_resting_hr_comes_from_sleep_summary(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT dm.resting_hr, ss.resting_hr FROM daily_metrics dm "
        "JOIN sleep_session ss ON ss.day = dm.day WHERE dm.day = ?",
        (FIXTURE_DAY.isoformat(),),
    ).fetchone() == (59, 59)


# ---------------------------------------------------------------------------
# readiness: daily_metrics.readiness/hrv_ms + resting_hr
# ---------------------------------------------------------------------------


def test_readiness_updates_readiness_and_hrv_ms(conn):
    client = FakeClient(readiness=readiness_payload(FIXTURE_DAY, rdns=70, hrv=65, rhr=48))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT readiness, hrv_ms FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone() == (70, 65.0)


def test_readiness_resting_hr_wins_over_band_data_when_present(conn):
    """sleepRHR coincide con el resting_hr de band_data en los días con solape
    se ingesta después para ganar cuando está presente."""
    client = FakeClient(readiness=readiness_payload(FIXTURE_DAY, rdns=70, hrv=65, rhr=48))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT resting_hr FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone()[0] == 48


def test_readiness_resting_hr_zero_does_not_clobber_band_data(conn):
    """0 lpm es un centinela, no un valor: no pisa el de band_data."""
    client = FakeClient(readiness=readiness_payload(FIXTURE_DAY, rdns=70, hrv=65, rhr=0))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT resting_hr FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone()[0] == 59


def test_readiness_stores_skin_temp_delta_in_celsius(conn):
    client = FakeClient(readiness=readiness_payload(FIXTURE_DAY, rdns=70, hrv=65, rhr=48, skinTempCalibrated=-12))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT skin_temp_delta FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone()[0] == -0.12


def test_readiness_skin_temp_sentinel_stays_null(conn):
    client = FakeClient(readiness=readiness_payload(FIXTURE_DAY, rdns=70, hrv=65, rhr=48, skinTempCalibrated=255))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT skin_temp_delta FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone()[0] is None


def test_readiness_with_no_items_does_not_touch_daily_metrics(conn):
    run.run_ingest(conn, FakeClient(), [FIXTURE_DAY], CONFIG)

    assert conn.execute(
        "SELECT readiness, hrv_ms FROM daily_metrics WHERE day = ?", (FIXTURE_DAY.isoformat(),)
    ).fetchone() == (None, None)


# ---------------------------------------------------------------------------
# hrv (HRVRMSSD): landing-first, sin persistir columnas (gana readiness.sleepHRV)
# ---------------------------------------------------------------------------


def test_hrv_lands_raw_without_creating_new_tables(conn):
    hrv_payload = {"items": [{"value": {"startTime": 1700000000000, "samples": []}}]}

    run.run_ingest(conn, FakeClient(hrv_rmssd=hrv_payload), [FIXTURE_DAY], CONFIG)

    assert conn.execute("SELECT payload FROM raw_ingest WHERE source = 'hrv'").fetchone()[0] == (
        json.dumps(hrv_payload, ensure_ascii=False)
    )
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "hrv_sample" not in tables


# ---------------------------------------------------------------------------
# stress: stress_sample + stress_avg (fuente all_day_stress)
# ---------------------------------------------------------------------------


def _utc_midnight_ts(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def test_stress_populates_stress_sample_table(conn):
    client = FakeClient(stress=all_day_stress_payload(FIXTURE_DAY, {0: 32, 300: 45}))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    start_ts = _utc_midnight_ts(FIXTURE_DAY)
    assert conn.execute("SELECT ts, value FROM stress_sample ORDER BY ts").fetchall() == [
        (start_ts, 32),
        (start_ts + 300 * 60, 45),
    ]


def test_stress_sample_ingest_is_idempotent(conn):
    client = FakeClient(stress=all_day_stress_payload(FIXTURE_DAY, {0: 32}))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)
    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    assert conn.execute("SELECT COUNT(*) FROM stress_sample").fetchone()[0] == 1


def test_stress_requests_the_day_window_from_its_utc_midnight(conn):
    """all_day_stress no tiene el desfase del blob: se pide el propio día, desde
    la medianoche UTC en la que empieza para traer los dos items que pisa."""
    client = FakeClient(stress=all_day_stress_payload(FIXTURE_DAY, {0: 32}))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    from_ms, to_ms = run._day_bounds_ms(FIXTURE_DAY, TZ)
    assert client.event_windows[("all_day_stress", None)] == (from_ms - from_ms % 86_400_000, to_ms)


def test_stress_reingest_replaces_the_whole_day(conn):
    """Una serie más corta debe BORRAR las filas sobrantes, no dejarlas huérfanas."""
    run.run_ingest(conn, FakeClient(stress=all_day_stress_payload(FIXTURE_DAY, {0: 32, 300: 45})), [FIXTURE_DAY], CONFIG)
    run.run_ingest(conn, FakeClient(stress=all_day_stress_payload(FIXTURE_DAY, {0: 32})), [FIXTURE_DAY], CONFIG)

    start_ts = _utc_midnight_ts(FIXTURE_DAY)
    assert conn.execute("SELECT ts, value FROM stress_sample ORDER BY ts").fetchall() == [
        (start_ts, 32)
    ]


def test_stress_avg_populates_daily_metrics(conn):
    """El agregado avgStress alimenta daily_metrics.stress_avg."""
    client = FakeClient(stress=all_day_stress_payload(FIXTURE_DAY, {0: 32}, avg=28))

    run.run_ingest(conn, client, [FIXTURE_DAY], CONFIG)

    day = datetime.fromtimestamp(_utc_midnight_ts(FIXTURE_DAY), timezone.utc).date().isoformat()
    assert conn.execute(
        "SELECT stress_avg FROM daily_metrics WHERE day = ?", (day,)
    ).fetchone()[0] == 28


# ---------------------------------------------------------------------------
# CLI: ventana de días
# ---------------------------------------------------------------------------


def test_build_days_default_window_ends_today():
    today = date(2026, 7, 22)
    assert run.build_days(today, days=3) == [
        date(2026, 7, 20),
        date(2026, 7, 21),
        date(2026, 7, 22),
    ]


def test_build_days_explicit_range_is_inclusive():
    days = run.build_days(date(2026, 7, 22), from_day=date(2026, 7, 1), to_day=date(2026, 7, 3))
    assert days == [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)]


def test_build_days_rejects_days_combined_with_range():
    with pytest.raises(SystemExit):
        run.build_days(date(2026, 7, 22), days=3, from_day=date(2026, 7, 1))


# ---------------------------------------------------------------------------
# Migración 002: índice único de raw_ingest sobre una DB preexistente con datos
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = Path(run.__file__).resolve().parent.parent / "db" / "migrations"


def _db_at_001(tmp_path: Path) -> Path:
    """DB con SOLO la migración 001 aplicada."""
    only_001 = tmp_path / "migrations_001"
    only_001.mkdir()
    (only_001 / "001_initial.sql").write_text(
        (MIGRATIONS_DIR / "001_initial.sql").read_text(), encoding="utf-8"
    )
    db_path = tmp_path / "legacy.db"
    assert db.init_db(db_path, only_001) == ["001"]
    return db_path


def test_migration_002_dedupes_existing_duplicates_and_keeps_the_newest(tmp_path):
    db_path = _db_at_001(tmp_path)
    with sqlite3.connect(db_path) as c:
        c.executemany(
            "INSERT INTO raw_ingest (source, day, fetched_at, payload) VALUES (?,?,?,?)",
            [
                ("band_data", "2026-07-20", 100, '{"n": 1}'),
                ("band_data", "2026-07-20", 200, '{"n": 2}'),
                ("band_data", "2026-07-20", 300, '{"n": 3}'),  # la más reciente
                ("biocharge", "2026-07-20", 100, '{"n": 4}'),
            ],
        )
    # Se comprueba que 002 entra, no que sea la única pendiente: fijar la lista
    # completa obligaba a tocar este test con cada migración nueva.
    assert "002" in db.init_db(db_path)

    with sqlite3.connect(db_path) as c:
        rows = c.execute(
            "SELECT source, day, payload FROM raw_ingest ORDER BY source"
        ).fetchall()
    assert rows == [
        ("band_data", "2026-07-20", '{"n": 3}'),
        ("biocharge", "2026-07-20", '{"n": 4}'),
    ]


def test_migration_002_makes_duplicates_impossible_afterwards(tmp_path):
    db_path = _db_at_001(tmp_path)
    db.init_db(db_path)

    with sqlite3.connect(db_path) as c:
        c.execute(
            "INSERT INTO raw_ingest (source, day, fetched_at, payload) VALUES ('s','2026-07-20',1,'{}')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(
                "INSERT INTO raw_ingest (source, day, fetched_at, payload) VALUES ('s','2026-07-20',2,'{}')"
            )


def test_migration_009_cleans_phantom_nights_and_zero_resting_hr(tmp_path):
    before_009 = tmp_path / "migrations_008"
    before_009.mkdir()
    for path in MIGRATIONS_DIR.glob("*.sql"):
        if path.name < "009":
            (before_009 / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    db_path = tmp_path / "legacy.db"
    db.init_db(db_path, before_009)

    # (day, start_ts, end_ts, resting_hr, is_nap, nº de fases)
    sessions = [
        ("2026-07-20", 1000, 1000, 0, 0, 0),  # fantasma: st == ed, sin fases
        ("2026-07-21", 2000, 1500, 0, 0, 1),  # ed < st (con una fase colgando)
        ("2026-07-22", 3000, 9000, 52, 0, 2),  # noche buena
        ("2026-07-23", 4000, 9000, 0, 0, 1),  # noche buena con rhr 0
        ("2026-07-24", 5000, 9000, 50, 0, 0),  # sin fases pero con duración: se queda
        ("2026-07-24", 6000, 7000, None, 1, 1),  # siesta
    ]
    with sqlite3.connect(db_path) as c:
        for day, start, end, rhr, is_nap, n_stages in sessions:
            session_id = c.execute(
                "INSERT INTO sleep_session (day, start_ts, end_ts, resting_hr, is_nap) VALUES (?,?,?,?,?)",
                (day, start, end, rhr, is_nap),
            ).lastrowid
            c.executemany(
                "INSERT INTO sleep_stage (session_id, start_ts, end_ts, stage) VALUES (?,?,?,4)",
                [(session_id, start, start + 60)] * n_stages,
            )
        c.executemany(
            "INSERT INTO daily_metrics (day, resting_hr) VALUES (?,?)",
            [("2026-07-20", 0), ("2026-07-22", 52)],
        )

    assert "009" in db.init_db(db_path)

    with sqlite3.connect(db_path) as c:
        assert c.execute(
            "SELECT day, start_ts, resting_hr, is_nap FROM sleep_session ORDER BY start_ts"
        ).fetchall() == [
            ("2026-07-22", 3000, 52, 0),
            ("2026-07-23", 4000, None, 0),
            ("2026-07-24", 5000, 50, 0),
            ("2026-07-24", 6000, None, 1),
        ]
        assert c.execute("SELECT COUNT(*) FROM sleep_stage").fetchone()[0] == 4
        assert c.execute(
            "SELECT COUNT(*) FROM sleep_stage WHERE session_id NOT IN (SELECT id FROM sleep_session)"
        ).fetchone()[0] == 0
        assert c.execute("SELECT day, resting_hr FROM daily_metrics ORDER BY day").fetchall() == [
            ("2026-07-20", None),
            ("2026-07-22", 52),
        ]


def test_store_raw_still_replaces_under_the_unique_index(conn):
    """El invariante de esquema no rompe el reemplazo que ya hacía store_raw."""
    run.store_raw(conn, "band_data", "2026-07-20", {"n": 1})
    run.store_raw(conn, "band_data", "2026-07-20", {"n": 2})

    rows = conn.execute(
        "SELECT payload FROM raw_ingest WHERE source='band_data' AND day='2026-07-20'"
    ).fetchall()
    assert rows == [('{"n": 2}',)]
