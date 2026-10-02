"""Orquestación de la ingesta: fetch → raw_ingest → parse → UPSERT idempotente.

Landing-first: el crudo se guarda y se COMMITEA en
``raw_ingest`` ANTES de parsear, para poder reprocesar sin re-tirar de la API
no oficial aunque el parser reviente. Un fallo en una fuente marca
``sync_state.status='error'`` para ese día y la ejecución CONTINÚA con las
demás fuentes.

``raw_ingest`` guarda el ÚLTIMO crudo por (source, day) — se reemplaza en cada
ejecución — para que correr N veces deje la misma cuenta de filas en todas las
tablas y el fichero no crezca sin límite.

Uso:
    uv run python -m ingest.run                       # ventana_dias del config, incremental
    uv run python -m ingest.run --days 3
    uv run python -m ingest.run --from 2026-07-01 --to 2026-07-15
    uv run python -m ingest.run --force                # ignora sync_state, repide toda la ventana
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from ingest import parsers
from ingest.auth import ZeppAuth
from ingest.client import ZeppClient
from ingest.config import load_config
from ingest.db import DEFAULT_DB_PATH, init_db

ROOT = Path(__file__).resolve().parent.parent

# Tablas cuyo conteo se imprime al final (criterio de idempotencia: correr dos
# veces seguidas debe dejar los mismos números).
COUNTED_TABLES = [
    "raw_ingest",
    "hr_minute",
    "sleep_session",
    "sleep_stage",
    "daily_metrics",
    "biocharge",
    "stress_sample",
    "workout",
    "sync_state",
]


# ---------------------------------------------------------------------------
# Bookkeeping y landing
# ---------------------------------------------------------------------------


def _fetch_ok_pairs(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """(source, day) ya confirmados 'ok' — usado por el filtro incremental."""
    rows = conn.execute("SELECT source, day FROM sync_state WHERE status = 'ok'").fetchall()
    return {(r[0], r[1]) for r in rows}


def set_sync_state(conn: sqlite3.Connection, source: str, day: str, status: str) -> None:
    """``last_ok_at`` solo avanza en 'ok'; en 'error' se conserva el anterior."""
    now = int(time.time())
    if status == "ok":
        conn.execute(
            "INSERT INTO sync_state (source, day, last_ok_at, status) VALUES (?,?,?,'ok') "
            "ON CONFLICT(source, day) DO UPDATE SET last_ok_at=excluded.last_ok_at, status='ok'",
            (source, day, now),
        )
    else:
        conn.execute(
            "INSERT INTO sync_state (source, day, last_ok_at, status) VALUES (?,?,NULL,?) "
            "ON CONFLICT(source, day) DO UPDATE SET status=excluded.status",
            (source, day, status),
        )
    conn.commit()


def store_raw(conn: sqlite3.Connection, source: str, day: str, payload: Any) -> None:
    """Guarda el crudo y COMMITEA: a partir de aquí el payload ya no se pierde."""
    conn.execute("DELETE FROM raw_ingest WHERE source = ? AND day = ?", (source, day))
    conn.execute(
        "INSERT INTO raw_ingest (source, day, fetched_at, payload) VALUES (?,?,?,?)",
        (source, day, int(time.time()), json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# UPSERTs (idempotentes)
# ---------------------------------------------------------------------------


def _upsert_hr(conn: sqlite3.Connection, samples: list[tuple[int, int]]) -> None:
    conn.executemany(
        "INSERT INTO hr_minute (ts, bpm) VALUES (?,?) "
        "ON CONFLICT(ts) DO UPDATE SET bpm=excluded.bpm",
        samples,
    )


def _upsert_stress(conn: sqlite3.Connection, samples: list[tuple[int, int]]) -> None:
    conn.executemany(
        "INSERT INTO stress_sample (ts, value) VALUES (?,?) "
        "ON CONFLICT(ts) DO UPDATE SET value=excluded.value",
        samples,
    )


def _upsert_biocharge(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO biocharge (ts, total, mental, physical, status) VALUES (?,?,?,?,?) "
        "ON CONFLICT(ts) DO UPDATE SET total=excluded.total, mental=excluded.mental, "
        "physical=excluded.physical, status=excluded.status",
        rows,
    )


def _upsert_sleep(conn: sqlite3.Connection, day: str, session: dict, stages: list[dict]) -> None:
    conn.execute(
        "INSERT INTO sleep_session (day, start_ts, end_ts, score, deep_min, light_min, "
        "rem_min, awake_min, wake_count, resting_hr, tz, is_nap) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(day, start_ts) DO UPDATE SET end_ts=excluded.end_ts, score=excluded.score, "
        "deep_min=excluded.deep_min, light_min=excluded.light_min, rem_min=excluded.rem_min, "
        "awake_min=excluded.awake_min, wake_count=excluded.wake_count, "
        "resting_hr=excluded.resting_hr, tz=excluded.tz, is_nap=excluded.is_nap",
        (
            day,
            session["start_ts"],
            session["end_ts"],
            session["score"],
            session["deep_min"],
            session["light_min"],
            session["rem_min"],
            session["awake_min"],
            session["wake_count"],
            session["resting_hr"],
            session["tz"],
            session.get("is_nap", 0),
        ),
    )
    session_id = conn.execute(
        "SELECT id FROM sleep_session WHERE day = ? AND start_ts = ?",
        (day, session["start_ts"]),
    ).fetchone()[0]
    # sleep_stage no tiene clave natural: se reemplaza el hipnograma entero.
    conn.execute("DELETE FROM sleep_stage WHERE session_id = ?", (session_id,))
    conn.executemany(
        "INSERT INTO sleep_stage (session_id, start_ts, end_ts, stage) VALUES (?,?,?,?)",
        [(session_id, s["start_ts"], s["end_ts"], s["stage"]) for s in stages],
    )


def _reconcile_naps(conn: sqlite3.Connection, day: str, naps: list[tuple[dict, list[dict]]]) -> None:
    """Borra las siestas del día que ya no aparecen en ``naps``.

    Los tramos ``odd_stage`` se reagrupan por contigüidad en cada corrida: si
    un re-fetch (hoy/ayer) rellena el hueco entre dos siestas, se fusionan en
    una sola con el ``start_ts`` de la primera. La fila vieja de la siesta
    absorbida tenía otro ``start_ts``, así que ON CONFLICT no la toca y
    quedaría huérfana para siempre si no se borra aquí.
    """
    kept_starts = {nap["start_ts"] for nap, _ in naps}
    stale = [
        row[0]
        for row in conn.execute(
            "SELECT id, start_ts FROM sleep_session WHERE day = ? AND is_nap = 1", (day,)
        ).fetchall()
        if row[1] not in kept_starts
    ]
    if stale:
        conn.executemany("DELETE FROM sleep_stage WHERE session_id = ?", [(i,) for i in stale])
        conn.executemany("DELETE FROM sleep_session WHERE id = ?", [(i,) for i in stale])


def _upsert_daily(conn: sqlite3.Connection, day: str, **fields: Any) -> None:
    """UPSERT parcial de ``daily_metrics``: solo toca las columnas recibidas.

    Varias fuentes escriben columnas distintas de la misma fila (band_data,
    DailyHealth, sport_load, vo2max, respiratory), así que cada una actualiza
    lo suyo sin pisar lo demás. Los nombres de columna son literales internos.
    """
    columns = list(fields)
    placeholders = ",".join("?" * (len(columns) + 1))
    updates = ",".join(f"{c}=excluded.{c}" for c in columns)
    conn.execute(
        f"INSERT INTO daily_metrics (day, {','.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(day) DO UPDATE SET {updates}",
        (day, *fields.values()),
    )


def _upsert_workouts(conn: sqlite3.Connection, workouts: list[dict], sport_types: dict) -> None:
    """UPSERT que preserva lo que ha escrito el usuario.

    ``review_status``, ``user_sport``, ``user_title`` y ``notes`` se fijan SOLO
    al INSERTAR: quedan fuera del ``DO UPDATE SET`` para que una re-ingesta no
    pise ni la clasificación de la cola ni las ediciones manuales. Es la misma
    regla que aísla la tabla ``annotation``: lo que escribe el usuario vive
    donde la ingesta no escribe.

    ``title`` SÍ se actualiza: es el ``sport_title`` que puso el usuario en la
    app de Zepp, o sea lo que dice la FUENTE. Si lo cambia allí, aquí se refleja;
    si quiere otro distinto, escribe ``user_title``, que gana al leer.
    """
    for w in workouts:
        avg_hr = w["avg_heart_rate"]
        conn.execute(
            "INSERT INTO workout (source, external_id, sport, sport_type, start_ts, end_ts, "
            "train_load, te, avg_hr, max_hr, hr_zones, strength_scores, auto_recognized, "
            "title, review_status, user_sport) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL) "
            "ON CONFLICT(source, external_id) DO UPDATE SET sport=excluded.sport, "
            "sport_type=excluded.sport_type, start_ts=excluded.start_ts, end_ts=excluded.end_ts, "
            "train_load=excluded.train_load, te=excluded.te, avg_hr=excluded.avg_hr, "
            "max_hr=excluded.max_hr, hr_zones=excluded.hr_zones, "
            "strength_scores=excluded.strength_scores, auto_recognized=excluded.auto_recognized, "
            "title=excluded.title",
            (
                "zepp",
                str(w["trackid"]),
                sport_types.get(str(w["type"])),
                w["type"],
                w["trackid"],
                w["end_time"],
                w["exercise_load"],
                w["te"],
                round(avg_hr) if avg_hr is not None else None,
                w["max_heart_rate"],
                w["heart_range"],
                w["strengthScores"],
                1 if w["auto_recognition"] else 0,
                w["sport_title"],
                w["review_status"],
            ),
        )


def derive_missing_hr(conn: sqlite3.Connection) -> int:
    """avg_hr/max_hr NULL → derivados de hr_minute en [start_ts, end_ts]."""
    rows = conn.execute(
        "SELECT id, start_ts, end_ts FROM workout "
        "WHERE (avg_hr IS NULL OR max_hr IS NULL) AND start_ts IS NOT NULL AND end_ts IS NOT NULL"
    ).fetchall()
    derived = 0
    for workout_id, start_ts, end_ts in rows:
        avg_bpm, max_bpm, samples = conn.execute(
            "SELECT AVG(bpm), MAX(bpm), COUNT(*) FROM hr_minute WHERE ts BETWEEN ? AND ?",
            (start_ts, end_ts),
        ).fetchone()
        if not samples:
            continue
        conn.execute(
            "UPDATE workout SET avg_hr = COALESCE(avg_hr, ?), max_hr = COALESCE(max_hr, ?) "
            "WHERE id = ?",
            (round(avg_bpm), max_bpm, workout_id),
        )
        derived += 1
    conn.commit()
    return derived


# ---------------------------------------------------------------------------
# Pipeline por fuente
# ---------------------------------------------------------------------------


def _day_bounds_ms(day: date, tz: str) -> tuple[int, int]:
    """Día local completo → (inicio_ms, fin_ms) unix UTC."""
    start = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(tz))
    return int(start.timestamp() * 1000), int((start + timedelta(days=1)).timestamp() * 1000)


# Cada fuente por día se parte en FETCH (solo red, se paraleliza) y PROCESS
# (parse + UPSERT con la única conexión sqlite, secuencial: sqlite no es
# thread-safe). Ver PER_DAY_SOURCES y run_ingest.


def fetch_band_data(client: Any, day: date, tz: str) -> Any:
    return client.band_data(day, day)


def process_band_data(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """band_data → hr_minute + sleep_session/sleep_stage + pasos/cal de daily_metrics."""
    store_raw(conn, "band_data", day.isoformat(), payload)

    for band_day in payload.get("data") or []:
        band_date = band_day["date_time"]
        if band_day.get("data_hr"):
            _upsert_hr(conn, parsers.parse_hr_minute(band_day, tz))

        summary_raw = band_day.get("summary")
        if not summary_raw:
            continue
        # Un día sin sueño registrado (pulsera quitada) trae summary sin 'slp':
        # no es un error, simplemente no hay sesión que guardar.
        if json.loads(base64.b64decode(summary_raw)).get("slp"):
            session, stages = parsers.parse_sleep(band_day, tz)
            _upsert_sleep(conn, band_date, session, stages)
            _upsert_daily(conn, band_date, tz=tz, resting_hr=session["resting_hr"])
            # Siestas (``odd_stage``): filas propias de sleep_session marcadas
            # con is_nap, que el esquema ya admitía por UNIQUE(day, start_ts).
            naps = parsers.parse_naps(band_day, tz)
            _reconcile_naps(conn, band_date, naps)
            for nap, nap_stages in naps:
                _upsert_sleep(conn, band_date, nap, nap_stages)

        daily = parsers.parse_daily_from_band(band_day)
        if daily:
            # Pasos/cal: DailyHealth manda (resumen curado del servidor) y se
            # ingiere DESPUÉS que band_data en el mismo día — ver
            # PER_DAY_SOURCES. Así band_data solo prevalece en los días que
            # DailyHealth no cubre, sin necesidad de estado entre fuentes.
            _upsert_daily(conn, band_date, tz=tz, steps=daily["steps"], calories=daily["calories"])
    conn.commit()


def fetch_readiness(client: Any, day: date, tz: str) -> Any:
    from_ms, to_ms = _day_bounds_ms(day, tz)
    return client.events("readiness", "watch_score", from_ms, to_ms)


def process_readiness(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """events readiness/watch_score → daily_metrics.readiness/hrv_ms/resting_hr.

    HRV: se persiste ``sleepHRV`` (curado por Zepp) en vez del agregado
    nocturno de HRVRMSSD/real_data — cruce empírico documentado en
    ``parsers.parse_readiness``. El agregado RMSSD queda solo en
    ``raw_ingest`` (ver ``process_hrv``), sin alimentar ninguna columna.

    resting_hr: ``sleepRHR`` coincidió EXACTO con el ``resting_hr`` derivado
    de band_data en los 3 días con solape. Se ingesta DESPUÉS de
    band_data para que gane cuando esté presente (cubre días sin resumen de
    sueño en band_data); en los días con solape no cambia nada porque ambos
    valores son iguales.
    """
    store_raw(conn, "readiness", day.isoformat(), payload)
    for entry in parsers.parse_readiness(payload, tz):
        fields: dict[str, Any] = {}
        if entry["readiness"] is not None:
            fields["readiness"] = entry["readiness"]
        if entry["sleepHRV"] is not None:
            fields["hrv_ms"] = entry["sleepHRV"]
        if entry["sleepRHR"] is not None:
            fields["resting_hr"] = entry["sleepRHR"]
        if fields:
            _upsert_daily(conn, entry["day"], **fields)
    conn.commit()


def fetch_hrv(client: Any, day: date, tz: str) -> Any:
    from_ms, to_ms = _day_bounds_ms(day, tz)
    return client.events("HRVRMSSD", "real_data", from_ms, to_ms)


def process_hrv(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """events HRVRMSSD/real_data → SOLO raw_ingest (landing-first: el crudo se guarda aunque no alimente ninguna columna).

    El agregado nocturno de estas muestras perdió el cruce contra
    ``readiness.sleepHRV`` (ambos coinciden en los días con solape, pero
    sleepHRV es el valor curado que muestra la app). Se conserva el crudo por
    si se reprocesa, pero no alimenta ninguna columna.
    """
    store_raw(conn, "hrv", day.isoformat(), payload)


def fetch_stress(client: Any, day: date, tz: str) -> Any:
    from_ms, to_ms = _day_bounds_ms(day, tz)
    return client.events_user("all_day_stress", from_ms, to_ms)


def process_stress(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """events all_day_stress (/users/{id}/events) → stress_sample + stress_avg.

    Fuente REAL de la serie de estrés que pinta la app. Sustituye al
    blob ``Charge/stress_data`` (curva modelo interna, ver
    ``parsers.parse_all_day_stress``): aquí cada muestra trae su ``time`` en
    epoch ms absoluto, sin anclajes ni truncados.

    El día se REEMPLAZA (DELETE del rango + INSERT) en vez de solo upsertar por
    ``ts``: si una re-ingesta trae menos muestras (día parcial), un upsert
    dejaría huérfanas las sobrantes. El agregado ``avgStress`` del día alimenta
    ``daily_metrics.stress_avg`` (UPSERT parcial, no pisa otras columnas).
    """
    store_raw(conn, "all_day_stress", day.isoformat(), payload)

    for block in parsers.parse_all_day_stress(payload, tz):
        conn.execute(
            "DELETE FROM stress_sample WHERE ts >= ? AND ts < ?",
            (block["start_ts"], block["end_ts"]),
        )
        _upsert_stress(conn, block["samples"])
        if block["avg_stress"] is not None:
            _upsert_daily(conn, block["day"], stress_avg=block["avg_stress"])
    conn.commit()


def fetch_biocharge(client: Any, day: date, tz: str) -> Any:
    from_ms, to_ms = _day_bounds_ms(day, tz)
    return client.events("Charge", "real_data", from_ms, to_ms)


def process_biocharge(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """events Charge/real_data → biocharge (1 muestra/min)."""
    store_raw(conn, "biocharge", day.isoformat(), payload)
    _upsert_biocharge(conn, parsers.parse_biocharge(payload))
    conn.commit()


def fetch_respiratory(client: Any, day: date, tz: str) -> Any:
    from_ms, to_ms = _day_bounds_ms(day, tz)
    return client.events("RespiratoryRate", "real_data", from_ms, to_ms)


def process_respiratory(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """events RespiratoryRate/real_data → daily_metrics.respiratory_rate (mediana).

    La serie intradía NO se persiste todavía (no hay tabla): el crudo queda en
    ``raw_ingest`` para reprocesarla cuando la haya. Se agrega por día UTC, que
    es como el propio payload trocea los items (índice 0 = medianoche UTC) y
    coincide con el ``dateString`` de DailyHealth.
    """
    store_raw(conn, "respiratory", day.isoformat(), payload)

    by_day: dict[str, list[int]] = {}
    for ts, rpm in parsers.parse_respiratory(payload):
        by_day.setdefault(datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), []).append(rpm)
    for day_key, samples in by_day.items():
        _upsert_daily(conn, day_key, respiratory_rate=median(samples))
    conn.commit()


def fetch_daily_health(client: Any, day: date, tz: str) -> Any:
    from_ms, to_ms = _day_bounds_ms(day, tz)
    return client.events("DailyHealth", "summary", from_ms, to_ms)


def process_daily_health(conn: sqlite3.Connection, payload: Any, day: date, tz: str) -> None:
    """events DailyHealth/summary → daily_metrics.steps/calories.

    Fuente PREFERENTE de pasos/calorías: es el resumen curado del servidor y
    llega más atrás que la ventana de band_data. Corre después de band_data
    (PER_DAY_SOURCES) para ganar el conflicto por orden de escritura.
    """
    store_raw(conn, "daily_health", day.isoformat(), payload)
    for entry in parsers.parse_daily_health(payload):
        _upsert_daily(conn, entry["day"], steps=entry["steps"], calories=entry["calories"])
    conn.commit()


def ingest_sport_load(conn: sqlite3.Connection, client: Any, days: list[date], config: dict) -> None:
    """SPORT_LOAD (endpoint de rango) → daily_metrics.train_load."""
    payload = client.sport_load(days[0], days[-1])
    store_raw(conn, "sport_load", days[-1].isoformat(), payload)
    for day_key, value in parsers.parse_sport_load(payload):
        _upsert_daily(conn, day_key, train_load=value)
    conn.commit()


def ingest_vo2max(conn: sqlite3.Connection, client: Any, days: list[date], config: dict) -> None:
    """VO2_MAX (endpoint de rango) → daily_metrics.vo2max."""
    payload = client.vo2max(days[0], days[-1])
    store_raw(conn, "vo2max", days[-1].isoformat(), payload)
    for day_key, value in parsers.parse_vo2max(payload):
        _upsert_daily(conn, day_key, vo2max=value)
    conn.commit()


def ingest_sport_history(
    conn: sqlite3.Connection, client: Any, days: list[date], config: dict
) -> None:
    """sport_history → workout. El endpoint NO filtra por día: un fetch por ejecución."""
    sport_types = config.get("sport_types") or {}
    payload = client.sport_history()
    store_raw(conn, "sport_history", days[-1].isoformat(), payload)
    _upsert_workouts(conn, parsers.parse_sport_history(payload, sport_types), sport_types)
    conn.commit()


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

# Máximo de GET de datos en paralelo. Los GET de datos NO
# registran sesión (ver docs/zepp-api.md, "Authentication"), así que concurrirlos no afecta al móvil ni dispara
# el 429 del login (que además es único, serializado por ZeppAuth._lock).
MAX_FETCH_WORKERS = 4

# Fuentes que se piden día a día, como (nombre, fetch, process). ORDEN
# SIGNIFICATIVO en el PROCESS: daily_health va después de band_data porque ambas
# escriben steps/calories y la política es que gane DailyHealth (resumen
# curado); band_data solo prevalece donde aquella no llega. readiness también va
# después de band_data por el mismo motivo con resting_hr: su sleepRHR
# gana cuando está presente. El FETCH, en cambio, se paraleliza (sin orden).
PER_DAY_SOURCES = [
    ("band_data", fetch_band_data, process_band_data),
    ("readiness", fetch_readiness, process_readiness),
    ("daily_health", fetch_daily_health, process_daily_health),
    ("biocharge", fetch_biocharge, process_biocharge),
    ("respiratory", fetch_respiratory, process_respiratory),
    ("hrv", fetch_hrv, process_hrv),
    ("all_day_stress", fetch_stress, process_stress),
]

# Fuentes cuyo endpoint cubre TODA la ventana de una vez (un fetch por
# ejecución); el bookkeeping se anota igualmente por día.
WINDOW_SOURCES = [
    ("sport_history", ingest_sport_history),
    ("sport_load", ingest_sport_load),
    ("vo2max", ingest_vo2max),
]


def run_ingest(
    conn: sqlite3.Connection,
    client: Any,
    days: list[date],
    config: dict,
    *,
    today: date | None = None,
    incremental: bool = True,
) -> dict:
    """Ejecuta el pipeline para ``days``.

    Sync incremental (sin él, una ventana de 30 días tardaba
    minutos): un ``(source, day)`` de ``PER_DAY_SOURCES`` que ya está en
    ``sync_state`` con ``status='ok'`` se salta, salvo que caiga dentro de
    ``safety_days`` desde ``today`` (datos de hoy/ayer son parciales o llegan
    con retraso del servidor). Auto-reparable: un día en ``'error'`` no está
    en el set de 'ok', así que se reintenta solo en el siguiente sync.
    ``WINDOW_SOURCES`` no se filtra: ya es coste fijo (1 petición/ejecución) y
    el servidor puede revisar retroactivamente días ya "cerrados".

    Devuelve {'ok': n, 'error': n, 'skipped': n, 'derived_hr': n}.
    """
    tz = config["tz"]
    today = today or max(days)
    safety_days = config.get("safety_days", 1)
    stats = {"ok": 0, "error": 0, "skipped": 0, "derived_hr": 0}

    ok_pairs = _fetch_ok_pairs(conn) if incremental else set()

    # Plan de (source, day) a pedir (los saltados por incremental no entran).
    plan: list[tuple[str, date, Any, Any]] = []
    for day in days:
        day_str = day.isoformat()
        always_fetch = (today - day).days <= safety_days
        for source, fetch, process in PER_DAY_SOURCES:
            if incremental and not always_fetch and (source, day_str) in ok_pairs:
                stats["skipped"] += 1
            else:
                plan.append((source, day, fetch, process))

    # Fase 1 (PARALELA): solo los GET (red). No se toca la BBDD aquí porque la
    # conexión sqlite no es thread-safe; el login es único (ZeppAuth._lock).
    payloads: dict[tuple[str, str], Any] = {}
    if plan:
        with ThreadPoolExecutor(max_workers=min(MAX_FETCH_WORKERS, len(plan))) as pool:
            futures = {
                pool.submit(fetch, client, day, tz): (source, day)
                for source, day, fetch, _process in plan
            }
            for future in as_completed(futures):
                source, day = futures[future]
                try:
                    payloads[(source, day.isoformat())] = future.result()
                except Exception as exc:  # fallo de red/fetch: se trata como error abajo
                    payloads[(source, day.isoformat())] = exc

    # Fase 2 (SECUENCIAL, orden de PER_DAY_SOURCES): parse + UPSERT con la única
    # conexión. Preserva la precedencia de daily_metrics e idempotencia.
    for day in days:
        day_str = day.isoformat()
        for source, _fetch, process in PER_DAY_SOURCES:
            key = (source, day_str)
            if key not in payloads:
                continue  # saltado por el filtro incremental
            payload = payloads[key]
            if isinstance(payload, Exception):
                set_sync_state(conn, source, day_str, "error")
                stats["error"] += 1
                print(f"  ERROR {source} {day_str}: {payload!r}", file=sys.stderr)
                continue
            try:
                process(conn, payload, day, tz)
            except Exception as exc:  # un parse roto no aborta el resto
                conn.rollback()  # el crudo ya está commiteado; se descarta el parse parcial
                set_sync_state(conn, source, day_str, "error")
                stats["error"] += 1
                print(f"  ERROR {source} {day_str}: {exc!r}", file=sys.stderr)
            else:
                set_sync_state(conn, source, day_str, "ok")
                stats["ok"] += 1

    for source, ingest in WINDOW_SOURCES:
        try:
            ingest(conn, client, days, config)
        except Exception as exc:
            conn.rollback()
            status = "error"
            stats["error"] += 1
            print(f"  ERROR {source}: {exc!r}", file=sys.stderr)
        else:
            status = "ok"
            stats["ok"] += 1
        # el fetch cubre la ventana entera -> se anota en todos sus días
        for day in days:
            set_sync_state(conn, source, day.isoformat(), status)

    stats["derived_hr"] = derive_missing_hr(conn)
    return stats


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in COUNTED_TABLES
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_days(
    today: date, *, days: int | None = None, from_day: date | None = None, to_day: date | None = None
) -> list[date]:
    if from_day is None and to_day is None:
        start, end = today - timedelta(days=days - 1), today
    else:
        if days is not None:
            raise SystemExit("--days no se combina con --from/--to")
        if from_day is None:
            raise SystemExit("--to requiere --from")
        start, end = from_day, to_day or today
    if start > end:
        raise SystemExit(f"rango vacío: {start.isoformat()} > {end.isoformat()}")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ingest.run", description="Ingesta Zepp: fetch → raw_ingest → parse → UPSERT."
    )
    parser.add_argument("--days", type=int, help="nº de días hacia atrás (default: ventana_dias)")
    parser.add_argument("--from", dest="from_day", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_day", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument(
        "--force",
        action="store_true",
        help="ignora sync_state y vuelve a pedir todos los días de la ventana",
    )
    args = parser.parse_args(argv)

    config = load_config()
    today = datetime.now(ZoneInfo(config["tz"])).date()
    if args.days is None and args.from_day is None and args.to_day is None:
        args.days = config["ventana_dias"]
    days = build_days(today, days=args.days, from_day=args.from_day, to_day=args.to_day)
    # --from/--to explícito es ya una señal de "quiero reprocesar esto sí o
    # sí" (p.ej. backfill dirigido tras arreglar un parser): si no se
    # desactivara el filtro ahí, se saltaría todo silenciosamente.
    incremental = not args.force and args.from_day is None

    init_db()
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    try:
        client = ZeppClient(ZeppAuth(config), config)
        print(f"Ventana: {days[0].isoformat()} → {days[-1].isoformat()} ({len(days)} día/s)")
        stats = run_ingest(conn, client, days, config, today=today, incremental=incremental)
        print(
            f"\nFuentes OK: {stats['ok']}  ·  con error: {stats['error']}  ·  "
            f"saltadas (ya sincronizadas): {stats['skipped']}  ·  "
            f"workouts con FC derivada: {stats['derived_hr']}"
        )
        print("Filas por tabla:")
        for table, count in table_counts(conn).items():
            print(f"  {table}: {count}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
