"""API FastAPI de zepp-dashboard: sirve series y agregados leídos de ``data/zepp.db``.

Convención de fechas
---------------------
Los query params de fecha (``date``, ``from``, ``to``) se reciben en formato
``YYYY-MM-DD`` **local** (zona horaria ``tz`` de ``ingest/config.toml`` —
la misma que usa ``ingest.run`` para anclar los días, default
``Europe/Madrid``). Las respuestas llevan los timestamps como **unix
segundos UTC** (``ts``) tal cual se guardan en BBDD; los datos inherentemente
diarios (p.ej. ``day`` de ``sleep_session``) devuelven el string local
``YYYY-MM-DD`` tal cual está en la fila.

Decisión pandas: NO se usa. Todos los endpoints son SELECTs directos o
agregados triviales (MAX/última fila por rango, join sesión→fases) que
SQLite resuelve sin necesitar un DataFrame intermedio; añadir pandas aquí
sería una dependencia sin beneficio.

Uso:
    uv run uvicorn backend.api:app --reload
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ingest import hevy, run
from ingest.auth import ZeppAuth
from ingest.client import ZeppClient
from ingest.config import load_config
from ingest.db import DEFAULT_DB_PATH, init_db

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
DEFAULT_TZ = "Europe/Madrid"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencias
# ---------------------------------------------------------------------------


def get_conn(request: Request):
    """Conexión por petición.

    ``check_same_thread=False`` es OBLIGATORIO aquí, no una relajación: FastAPI
    resuelve una dependencia generadora síncrona y el endpoint en DOS envíos
    distintos al threadpool (``run_in_threadpool(cm.__enter__)`` y luego
    ``run_in_threadpool(dependant.call)``), y anyio no garantiza que ambos
    caigan en el mismo worker. Sin esto, en cuanto hay varias peticiones a la
    vez la conexión se crea en un hilo y se usa en otro → ProgrammingError
    ("SQLite objects created in a thread can only be used in that same
    thread") y un 500 intermitente en CUALQUIER endpoint.

    Sigue siendo seguro: cada petición abre SU propia conexión y solo la usa un
    hilo a la vez (crear → consultar → cerrar es secuencial); lo que la bandera
    desactiva es la comprobación de identidad de hilo, no la exclusión mutua.
    """
    conn = sqlite3.connect(request.app.state.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def require_auth(request: Request) -> None:
    """Bearer token OPCIONAL: sin ``api_token`` en config, todo /api/* queda
    abierto (uso previsto tras Tailscale)."""
    token = request.app.state.api_token
    if not token:
        return
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or value != token:
        raise HTTPException(status_code=401, detail="unauthorized")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _day_range_ts(day_from: date, day_to: date, tz: str) -> tuple[int, int]:
    """[día_from, día_to] local -> [inicio, fin) en unix segundos UTC."""
    if day_from > day_to:
        raise HTTPException(status_code=400, detail="'from' debe ser <= 'to'")
    zone = ZoneInfo(tz)
    start = datetime(day_from.year, day_from.month, day_from.day, tzinfo=zone)
    end = datetime(day_to.year, day_to.month, day_to.day, tzinfo=zone) + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


# Downsampling en servidor: las series por minuto crecían sin límite con
# el rango (30d ≈ 43k puntos / >1 MB) y congelaban el front. Se
# agrega por buckets con SQL (media por bucket) manteniendo la forma de fila
# `{ts, ...}` que ya consumía el front. ``ts`` pasa a ser el INICIO del bucket.
MAX_SERIES_POINTS = 2500
_BUCKET_LADDER_S = (60, 300, 900, 1800, 3600)  # 1min, 5min, 15min, 30min, 1h


def _auto_bucket(start_ts: int, end_ts: int) -> int:
    """Bucket (segundos) más fino de la escala que deja el rango ≤ 2.500 puntos.

    Rangos típicos: hoy (1d) -> 60s, 7d -> 300s, 30d -> 1800s. El tope 2.500 es
    30d cae en 30min porque a 15min serían ~2.880 puntos, por encima del tope.
    """
    span = max(end_ts - start_ts, 1)
    for bucket in _BUCKET_LADDER_S:
        if span / bucket <= MAX_SERIES_POINTS:
            return bucket
    return _BUCKET_LADDER_S[-1]


def _downsample(
    conn: sqlite3.Connection,
    table: str,
    value_exprs: list[tuple[str, str]],
    start_ts: int,
    end_ts: int,
    bucket: int,
) -> list[dict[str, Any]]:
    """Agrega ``table`` en buckets de ``bucket`` s sobre [start_ts, end_ts).

    El GROUP BY solo emite buckets CON datos. Cuando dos buckets consecutivos
    distan >1 bucket hay un hueco real: se inserta un marcador ``{ts, ...: None}``
    entre ellos para que el front CORTE la línea (``connectNulls=false``) en vez
    de interpolar sobre minutos sin muestra ("un hueco es un hueco").

    ``value_exprs`` son pares (alias, expresión SQL agregada), p.ej.
    ``("bpm", "CAST(ROUND(AVG(bpm)) AS INTEGER)")``. ``table``/expresiones son
    literales internos (no entran valores de usuario en el SQL).
    """
    select = ", ".join(f"{expr} AS {alias}" for alias, expr in value_exprs)
    aliases = [alias for alias, _ in value_exprs]
    rows = conn.execute(
        f"SELECT (ts / ?) * ? AS bts, {select} FROM {table} "
        "WHERE ts >= ? AND ts < ? GROUP BY bts ORDER BY bts",
        (bucket, bucket, start_ts, end_ts),
    ).fetchall()

    series: list[dict[str, Any]] = []
    prev_bts: int | None = None
    for r in rows:
        bts = r["bts"]
        if prev_bts is not None and bts - prev_bts > bucket:
            series.append({"ts": prev_bts + bucket, **{alias: None for alias in aliases}})
        series.append({"ts": bts, **{alias: r[alias] for alias in aliases}})
        prev_bts = bts
    return series


def _series_stats(
    conn: sqlite3.Connection, table: str, column: str, start_ts: int, end_ts: int
) -> dict[str, Any]:
    """min/avg/max EXACTOS sobre el CRUDO del rango: las tarjetas no deben
    mostrar la media de los buckets (aplanaba p.ej. el pico de FC) sino el
    extremo real. ``NULL`` en cada campo si el rango no tiene muestras."""
    row = conn.execute(
        f"SELECT MIN({column}) AS min, AVG({column}) AS avg, MAX({column}) AS max "
        f"FROM {table} WHERE ts >= ? AND ts < ?",
        (start_ts, end_ts),
    ).fetchone()
    return {"min": row["min"], "avg": row["avg"], "max": row["max"]}


def parse_hr_zones(raw: str | None) -> list[dict[str, int]]:
    """'heart_range' crudo: pares 'segundos,umbral' separados por ';'.

    Ver ``docs/zepp-api.md``."""
    if not raw:
        return []
    zones = []
    for pair in raw.split(";"):
        if not pair:
            continue
        seconds_str, threshold_str = pair.split(",")
        zones.append({"seconds": int(seconds_str), "threshold": int(threshold_str)})
    return zones


def _effective_sport(row: sqlite3.Row) -> str | None:
    """Tipo que manda al pintar: lo que dijo el usuario y, si no ha dicho nada,
    el nombre del mapa ``sport_types``. ``None`` = code desconocido sin revisar
    (la UI lo etiqueta "Sin clasificar")."""
    return row["user_sport"] or row["sport"]


def _hevy_exercises(conn: sqlite3.Connection, workout_id: int) -> list[dict[str, Any]]:
    """Series agrupadas por ejercicio, en el orden del CSV.

    El corte es por ejercicio CONSECUTIVO, no por un GROUP BY: hacer el mismo
    movimiento en dos momentos de la sesión son dos bloques en Hevy y así se
    ven en la tabla."""
    rows = conn.execute(
        "SELECT exercise, muscle_group, set_index, reps, weight_kg, rpe, set_type "
        "FROM workout_set WHERE workout_id = ? ORDER BY id",
        (workout_id,),
    ).fetchall()

    groups: list[dict[str, Any]] = []
    for r in rows:
        if not groups or groups[-1]["exercise"] != r["exercise"]:
            groups.append({"exercise": r["exercise"], "muscle_group": r["muscle_group"], "sets": []})
        groups[-1]["sets"].append(
            {
                "set_index": r["set_index"],
                "reps": r["reps"],
                "weight_kg": r["weight_kg"],
                "rpe": r["rpe"],
                "set_type": r["set_type"],
            }
        )
    return groups


def _hevy_muscles(conn: sqlite3.Connection, workout_id: int) -> list[dict[str, Any]]:
    """Músculos tocados por la sesión con su intensidad (join ``exercise_muscle``).

    Se queda con el MÁXIMO por músculo, no la suma: la intensidad es "cuánto
    entra este músculo en el ejercicio" (0-1), no una cantidad acumulable —
    sumarla daría 2.4 de pecho y rompería la escala. El volumen por músculo
    (que sí acumula) lo calcula ``/api/muscles/volume``."""
    rows = conn.execute(
        "SELECT em.muscle AS muscle, MAX(em.intensity) AS intensity FROM workout_set ws "
        "JOIN exercise_muscle em ON em.exercise = ws.exercise "
        "WHERE ws.workout_id = ? GROUP BY em.muscle ORDER BY intensity DESC, muscle",
        (workout_id,),
    ).fetchall()
    return [{"muscle": r["muscle"], "intensity": r["intensity"]} for r in rows]


def _strap_data(conn: sqlite3.Connection, linked_id: int) -> dict[str, Any] | None:
    """Lado fisiológico del entreno de Hevy: el workout del strap vinculado."""
    row = conn.execute(
        "SELECT id, sport_type, start_ts, end_ts, train_load, te, avg_hr, max_hr, hr_zones "
        "FROM workout WHERE id = ?",
        (linked_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "sport_type": row["sport_type"],
        "start_ts": row["start_ts"],
        "end_ts": row["end_ts"],
        "train_load": row["train_load"],
        "te": row["te"],
        "avg_hr": row["avg_hr"],
        "max_hr": row["max_hr"],
        "hr_zones": parse_hr_zones(row["hr_zones"]),
    }


def _serialize_workout(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    data = {
        "id": row["id"],
        "source": row["source"],
        "external_id": row["external_id"],
        "title": row["title"],
        "user_title": row["user_title"],
        # Lo que se pinta: manda lo que escribió el usuario y, si no ha escrito
        # nada, el nombre que trae la fuente (``sport_title`` de Zepp o el
        # título del entreno de Hevy). Misma regla que ``effective_sport``.
        "effective_title": row["user_title"] or row["title"],
        "notes": row["notes"],
        "sport": row["sport"],
        "sport_type": row["sport_type"],
        "effective_sport": _effective_sport(row),
        "start_ts": row["start_ts"],
        "end_ts": row["end_ts"],
        "duration_s": (
            row["end_ts"] - row["start_ts"]
            if row["start_ts"] is not None and row["end_ts"] is not None
            else None
        ),
        "train_load": row["train_load"],
        "te": row["te"],
        "avg_hr": row["avg_hr"],
        "max_hr": row["max_hr"],
        "hr_zones": parse_hr_zones(row["hr_zones"]),
        "strength_scores": json.loads(row["strength_scores"]) if row["strength_scores"] else None,
        "auto_recognized": bool(row["auto_recognized"]),
        "review_status": row["review_status"],
        "user_sport": row["user_sport"],
        "linked_workout_id": row["linked_workout_id"],
    }
    if conn is not None and row["start_ts"] is not None and row["end_ts"] is not None:
        hr_rows = conn.execute(
            "SELECT ts, bpm FROM hr_minute WHERE ts BETWEEN ? AND ? ORDER BY ts",
            (row["start_ts"], row["end_ts"]),
        ).fetchall()
        data["hr_overlay"] = [{"ts": r["ts"], "bpm": r["bpm"]} for r in hr_rows]
    if conn is not None and row["source"] == "hevy":
        data["exercises"] = _hevy_exercises(conn, row["id"])
        data["muscles"] = _hevy_muscles(conn, row["id"])
        data["strap"] = _strap_data(conn, row["linked_workout_id"]) if row["linked_workout_id"] else None
    return data


def _local_day(ts: int, tz: str) -> str:
    return datetime.fromtimestamp(ts, ZoneInfo(tz)).date().isoformat()


def _hevy_evidence(conn: sqlite3.Connection, start_ts: int | None, tz: str) -> dict[str, Any] | None:
    """Entreno de Hevy del mismo día local SIN vincular, si lo hay.

    Es la pista que convierte "¿qué hiciste aquí?" en una pregunta contestable:
    un 223 suelto no dice nada, pero si ese día hay un 'Entrenamiento 💪' con 12
    series registrado a mano y sin strap asociado, casi seguro es este.
    """
    if start_ts is None:
        return None
    day = _local_day(start_ts, tz)
    rows = conn.execute(
        "SELECT w.id, w.title, w.start_ts, w.end_ts, "
        "(SELECT COUNT(*) FROM workout_set ws WHERE ws.workout_id = w.id) AS n_sets "
        "FROM workout w WHERE w.source = 'hevy' AND w.linked_workout_id IS NULL "
        "AND w.start_ts IS NOT NULL ORDER BY w.start_ts"
    ).fetchall()
    for r in rows:
        if _local_day(r["start_ts"], tz) != day:
            continue
        return {
            "id": r["id"],
            "title": r["title"],
            "n_sets": r["n_sets"],
            "duration_s": r["end_ts"] - r["start_ts"] if r["end_ts"] is not None else None,
        }
    return None


# ---------------------------------------------------------------------------
# Endpoints de lectura
# ---------------------------------------------------------------------------


@router.get("/api/overview")
def get_overview(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_param: date | None = Query(None, alias="date"),
):
    tz = request.app.state.tz
    day = date_param or datetime.now(ZoneInfo(tz)).date()
    day_str = day.isoformat()
    start_ts, end_ts = _day_range_ts(day, day, tz)

    biocharge_row = conn.execute(
        "SELECT ts, total, mental, physical, status FROM biocharge "
        "WHERE ts >= ? AND ts < ? ORDER BY ts DESC LIMIT 1",
        (start_ts, end_ts),
    ).fetchone()
    biocharge = dict(biocharge_row) if biocharge_row else None
    if biocharge is not None:
        # La muestra más reciente puede traer `total` NULL (el
        # servidor lo computa con más retraso que mental/physical) mientras
        # una muestra un poco anterior sí lo tiene. Rellenar cada campo por
        # separado con su último valor no-nulo evita "Sin datos" espurio en
        # el total cuando mental/physical sí están.
        for field in ("total", "mental", "physical"):
            if biocharge[field] is not None:
                continue
            fallback = conn.execute(
                f"SELECT {field} FROM biocharge WHERE ts >= ? AND ts < ? "
                f"AND {field} IS NOT NULL ORDER BY ts DESC LIMIT 1",
                (start_ts, end_ts),
            ).fetchone()
            if fallback is not None:
                biocharge[field] = fallback[field]

    metrics_row = conn.execute(
        "SELECT readiness, steps FROM daily_metrics WHERE day = ?", (day_str,)
    ).fetchone()

    # ``is_nap = 0``: la tarjeta es del sueño NOCTURNO. Sin este filtro, una
    # siesta de las 22:30 sería la última sesión del día y la tarjeta mostraría
    # 40 minutos en vez de 8 horas.
    sleep_row = conn.execute(
        "SELECT start_ts, end_ts, score FROM sleep_session WHERE day = ? AND is_nap = 0 "
        "ORDER BY start_ts DESC LIMIT 1",
        (day_str,),
    ).fetchone()

    # Peor status + último OK entre las fuentes: solo se mira el día MÁS
    # RECIENTE que cada fuente haya intentado (no todo el histórico, para no
    # arrastrar un error viejo ya resuelto). Señal de fallo silencioso

    sync_rows = conn.execute(
        "SELECT s1.status, s1.last_ok_at FROM sync_state s1 "
        "WHERE s1.day = (SELECT MAX(s2.day) FROM sync_state s2 WHERE s2.source = s1.source)"
    ).fetchall()
    last_ok_at = None
    worst_status = "ok"
    for r in sync_rows:
        if r["last_ok_at"] is not None:
            last_ok_at = r["last_ok_at"] if last_ok_at is None else max(last_ok_at, r["last_ok_at"])
        if r["status"] != "ok":
            worst_status = "error"

    return {
        "date": day_str,
        "biocharge": biocharge,
        "readiness": metrics_row["readiness"] if metrics_row else None,
        "steps": metrics_row["steps"] if metrics_row else None,
        "sleep": (
            {
                "score": sleep_row["score"],
                "duration_min": round((sleep_row["end_ts"] - sleep_row["start_ts"]) / 60),
            }
            if sleep_row and sleep_row["start_ts"] is not None and sleep_row["end_ts"] is not None
            else None
        ),
        "last_sync": {"ts": last_ok_at, "status": worst_status if sync_rows else "unknown"},
    }


@router.get("/api/daily")
def get_daily(
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
):
    """Filas de ``daily_metrics`` del rango [from, to], una por día CON datos.

    Se filtra por el string ``day`` y no por ts (como ``/api/sleep``): la tabla
    ya está indexada por día LOCAL, convertir a unix y volver solo añadiría
    sitios donde equivocarse con el DST.

    ``SELECT *`` a propósito: es una tabla wide que rellenan varios jobs por
    separado (pasos, readiness, estrés, vo2max…) y una columna nueva en una
    migración debe llegar al cliente sin tocar este endpoint. Los días sin fila
    NO se rellenan aquí: un hueco es un hueco (no hubo ingesta), y quien pinta
    decide si lo dibuja vacío o lo salta.
    """
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="'from' debe ser <= 'to'")
    rows = conn.execute(
        "SELECT * FROM daily_metrics WHERE day BETWEEN ? AND ? ORDER BY day",
        (date_from.isoformat(), date_to.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/hr")
def get_hr(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    bucket: int | None = Query(None, ge=1),
):
    start_ts, end_ts = _day_range_ts(date_from, date_to, request.app.state.tz)
    bucket = bucket or _auto_bucket(start_ts, end_ts)
    return {
        "series": _downsample(
            conn, "hr_minute", [("bpm", "CAST(ROUND(AVG(bpm)) AS INTEGER)")], start_ts, end_ts, bucket
        ),
        "stats": _series_stats(conn, "hr_minute", "bpm", start_ts, end_ts),
    }


@router.get("/api/stress")
def get_stress(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    bucket: int | None = Query(None, ge=1),
):
    start_ts, end_ts = _day_range_ts(date_from, date_to, request.app.state.tz)
    bucket = bucket or _auto_bucket(start_ts, end_ts)
    return {
        "series": _downsample(
            conn, "stress_sample", [("value", "CAST(ROUND(AVG(value)) AS INTEGER)")], start_ts, end_ts, bucket
        ),
        "stats": _series_stats(conn, "stress_sample", "value", start_ts, end_ts),
    }


@router.get("/api/biocharge")
def get_biocharge(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    bucket: int | None = Query(None, ge=1),
):
    start_ts, end_ts = _day_range_ts(date_from, date_to, request.app.state.tz)
    bucket = bucket or _auto_bucket(start_ts, end_ts)
    return _downsample(
        conn,
        "biocharge",
        [
            ("total", "ROUND(AVG(total), 1)"),
            ("mental", "ROUND(AVG(mental), 1)"),
            ("physical", "ROUND(AVG(physical), 1)"),
            ("status", "MAX(status)"),
        ],
        start_ts,
        end_ts,
        bucket,
    )


@router.get("/api/sleep")
def get_sleep(
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="'from' debe ser <= 'to'")
    sessions = conn.execute(
        "SELECT id, day, start_ts, end_ts, score, deep_min, light_min, rem_min, awake_min, "
        "wake_count, resting_hr, tz, is_nap FROM sleep_session "
        "WHERE day BETWEEN ? AND ? ORDER BY start_ts",
        (date_from.isoformat(), date_to.isoformat()),
    ).fetchall()
    result = []
    for session in sessions:
        stages = conn.execute(
            "SELECT start_ts, end_ts, stage FROM sleep_stage WHERE session_id = ? ORDER BY start_ts",
            (session["id"],),
        ).fetchall()
        item = dict(session)
        item["is_nap"] = bool(session["is_nap"])
        item["stages"] = [dict(s) for s in stages]
        result.append(item)
    return result


@router.get("/api/workouts")
def get_workouts(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    include_ignored: bool = Query(False),
):
    """Workouts del rango, uno por sesión REAL.

    **Regla de absorción**: un workout del strap que ya está vinculado desde
    Hevy (``hevy.linked_workout_id = zepp.id``) NO se lista aparte. Son el mismo
    entreno visto por dos aparatos: el de Hevy trae el qué (ejercicio, series,
    peso, músculo) y absorbe del strap el cómo (FC, zonas, carga, TE) en su
    campo ``strap``. Listar los dos duplicaría la sesión en la lista y contaría
    doble en cualquier agregado.
    """
    start_ts, end_ts = _day_range_ts(date_from, date_to, request.app.state.tz)
    # Los descartados están OCULTOS por defecto, no borrados: se piden aparte
    # para poder recuperarlos. Sin esta puerta, 'ignored' era un viaje de ida.
    keep = "" if include_ignored else "review_status != 'ignored' AND "
    rows = conn.execute(
        f"SELECT * FROM workout WHERE {keep}start_ts >= ? AND start_ts < ? "
        "AND id NOT IN (SELECT linked_workout_id FROM workout WHERE linked_workout_id IS NOT NULL) "
        "ORDER BY start_ts DESC",
        (start_ts, end_ts),
    ).fetchall()
    return [_serialize_workout(r, conn) for r in rows]


@router.get("/api/muscles/volume")
def get_muscles_volume(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
):
    """Volumen de fuerza por músculo del rango: ``Σ(peso_kg × reps × intensity)``.

    ``intensity`` (0-1, tabla ``exercise_muscle``) reparte cada serie entre los
    músculos que trabaja: un press inclinado suma entero al pecho y a la mitad
    al tríceps. Por eso la suma de los músculos NO es "el peso movido": es
    volumen ponderado, comparable entre músculos, que es lo que normaliza el
    body-map.

    Qué queda fuera:

    - **Calentamiento** (``set_type='warmup'``): no es carga de trabajo. Las
      series siguen guardadas, solo no cuentan aquí
      ni en ``sets``.
    - **Workouts ``ignored``**: falsos positivos que el usuario ya descartó en
      la cola de revisión.

    Una serie sin peso o sin reps (registro incompleto) aporta 0 al volumen
    pero sí cuenta como serie efectiva: la hizo.
    """
    start_ts, end_ts = _day_range_ts(date_from, date_to, request.app.state.tz)
    # Agregado por (músculo, ejercicio) de una vez: el top-3 sale de las mismas
    # filas ya ordenadas por volumen, sin una segunda consulta por músculo.
    rows = conn.execute(
        "SELECT em.muscle AS muscle, ws.exercise AS exercise, COUNT(*) AS sets, "
        "SUM(COALESCE(ws.weight_kg, 0) * COALESCE(ws.reps, 0) * em.intensity) AS volume "
        "FROM workout_set ws "
        "JOIN exercise_muscle em ON em.exercise = ws.exercise "
        "JOIN workout w ON w.id = ws.workout_id "
        "WHERE w.start_ts >= ? AND w.start_ts < ? AND w.review_status != 'ignored' "
        "AND COALESCE(ws.set_type, 'normal') != 'warmup' "
        "GROUP BY em.muscle, ws.exercise ORDER BY volume DESC",
        (start_ts, end_ts),
    ).fetchall()

    muscles: dict[str, dict[str, Any]] = {}
    for r in rows:
        muscle = muscles.setdefault(
            r["muscle"], {"muscle": r["muscle"], "volume": 0.0, "sets": 0, "top_exercises": []}
        )
        muscle["volume"] += r["volume"]
        muscle["sets"] += r["sets"]
        if len(muscle["top_exercises"]) < 3:
            muscle["top_exercises"].append(
                {"exercise": r["exercise"], "volume": round(r["volume"], 1), "sets": r["sets"]}
            )

    items = sorted(muscles.values(), key=lambda m: -m["volume"])
    total = round(sum(m["volume"] for m in items), 1)
    for m in items:
        m["volume"] = round(m["volume"], 1)
    return {"from": date_from.isoformat(), "to": date_to.isoformat(), "total_volume": total, "muscles": items}


@router.get("/api/sports")
def get_sports(conn: sqlite3.Connection = Depends(get_conn)):
    """Etiquetas de deporte con su color: el desplegable y la paleta.

    Une TRES fuentes, porque una categoría puede existir por tres motivos
    distintos y ninguno es más válido que otro:

    - ``workout.sport`` — la trajo el mapa ``[sport_types]`` de tu config.
    - ``workout.user_sport`` — la escribiste al clasificar un entreno. Escribir
      una categoría una vez sigue siendo suficiente para crearla.
    - ``sport_style.sport`` — la creaste a mano, quizá antes de usarla nunca.

    ``color`` es ``null`` si no le has elegido ninguno; el front cae entonces en
    su hash determinista, que ya da un color estable a cada nombre.
    """
    rows = conn.execute(
        "SELECT name, (SELECT color FROM sport_style s WHERE s.sport = name) AS color FROM ("
        "  SELECT DISTINCT sport AS name FROM workout WHERE sport IS NOT NULL"
        "  UNION SELECT DISTINCT user_sport FROM workout WHERE user_sport IS NOT NULL"
        "  UNION SELECT sport FROM sport_style"
        ") ORDER BY name"
    ).fetchall()
    return [{"name": r["name"], "color": r["color"]} for r in rows]


class SportStyle(BaseModel):
    color: str | None = None


@router.put("/api/sports/{name}")
def put_sport(name: str, body: SportStyle, conn: sqlite3.Connection = Depends(get_conn)):
    """Crea la etiqueta o le cambia el color. Es el mismo gesto: una etiqueta
    sin entrenos es una fila aquí, y ponerle color es esta misma fila."""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="el nombre no puede estar vacío")
    conn.execute(
        "INSERT INTO sport_style (sport, color) VALUES (?,?) "
        "ON CONFLICT(sport) DO UPDATE SET color=excluded.color",
        (name, body.color),
    )
    conn.commit()
    return {"name": name, "color": body.color}


@router.delete("/api/sports/{name}", status_code=204)
def delete_sport(name: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Quita el color y la etiqueta vacía. **No toca los entrenos**: si alguno
    la tiene en ``user_sport``, la categoría sigue existiendo por uso y vuelve a
    salir en la lista, ya sin color. Borrar una etiqueta no puede ser una forma
    encubierta de reclasificar entrenos."""
    conn.execute("DELETE FROM sport_style WHERE sport = ?", (name.strip(),))
    conn.commit()


@router.get("/api/workouts/pending")
def get_workouts_pending(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    tz = request.app.state.tz
    rows = conn.execute(
        "SELECT * FROM workout WHERE review_status = 'pending' ORDER BY start_ts"
    ).fetchall()
    result = []
    for row in rows:
        item = _serialize_workout(row)
        item["hevy_evidence"] = _hevy_evidence(conn, row["start_ts"], tz)
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Anotaciones manuales sobre la línea de tiempo
# ---------------------------------------------------------------------------


class AnnotationIn(BaseModel):
    start_ts: int
    end_ts: int
    text: str


def _serialize_annotation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "start_ts": row["start_ts"],
        "end_ts": row["end_ts"],
        "text": row["text"],
        "created_at": row["created_at"],
    }


@router.get("/api/annotations")
def get_annotations(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
):
    """Anotaciones que SOLAPAN con el rango, no solo las que empiezan dentro:
    un tramo que arranca a las 23:30 y cruza la medianoche debe seguir
    saliendo al mirar el día siguiente."""
    start_ts, end_ts = _day_range_ts(date_from, date_to, request.app.state.tz)
    rows = conn.execute(
        "SELECT * FROM annotation WHERE start_ts < ? AND end_ts >= ? ORDER BY start_ts",
        (end_ts, start_ts),
    ).fetchall()
    return [_serialize_annotation(r) for r in rows]


@router.post("/api/annotations", status_code=201)
def post_annotation(body: AnnotationIn, conn: sqlite3.Connection = Depends(get_conn)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="el texto no puede estar vacío")
    if body.end_ts < body.start_ts:
        raise HTTPException(status_code=400, detail="'end_ts' debe ser >= 'start_ts'")
    cursor = conn.execute(
        "INSERT INTO annotation (start_ts, end_ts, text, created_at) VALUES (?, ?, ?, ?)",
        (body.start_ts, body.end_ts, text, int(time.time())),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM annotation WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize_annotation(row)


@router.delete("/api/annotations/{annotation_id}", status_code=204)
def delete_annotation(annotation_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    cursor = conn.execute("DELETE FROM annotation WHERE id = ?", (annotation_id,))
    conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="anotación no encontrada")


# ---------------------------------------------------------------------------
# Cola de revisión
# ---------------------------------------------------------------------------


class WorkoutReview(BaseModel):
    action: Literal["classify", "ignore", "restore"]
    sport: str | None = None


def _resync_strap_link(
    conn: sqlite3.Connection, request: Request, workout_id: int, sport: str | None
) -> None:
    """Rehace el vínculo Hevy↔strap tras cambiar el tipo de un entreno.

    Si pasa a ser fuerza y ese día hay un entreno de Hevy sin vincular, se
    vincula con el MISMO efecto que el import (``hevy.link_to_strap``:
    ``linked_workout_id`` + la ventana horaria del strap sobreescribiendo la del
    CSV, que la teclea el usuario). Si deja de serlo, se suelta el vínculo: si
    no, quedaría un overlay de FC colgado de un entreno que el usuario dice que
    no era eso.
    """
    strength_sport = request.app.state.strength_sport
    if sport == strength_sport:
        hevy.link_to_strap(conn, request.app.state.tz, strength_sport)
    else:
        conn.execute(
            "UPDATE workout SET linked_workout_id = NULL WHERE linked_workout_id = ?", (workout_id,)
        )


@router.post("/api/workouts/{workout_id}/review")
def post_workout_review(
    workout_id: int,
    body: WorkoutReview,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Clasifica, descarta o recupera un workout.

    Clasificar como fuerza (``strength_sport`` del config) además lo mete en el
    matching de Hevy — ver ``_resync_strap_link``.

    ``restore`` deshace un ``ignore``: lo devuelve a la cola. Descartar oculta,
    no borra (un workout de Zepp volvería en el siguiente sync de todas formas),
    así que tiene que haber camino de vuelta.
    """
    row = conn.execute("SELECT * FROM workout WHERE id = ?", (workout_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="workout no encontrado")

    if body.action == "classify":
        if not body.sport:
            raise HTTPException(status_code=400, detail="'sport' requerido para action=classify")
        conn.execute(
            "UPDATE workout SET review_status = 'classified', user_sport = ? WHERE id = ?",
            (body.sport, workout_id),
        )
    elif body.action == "restore":
        conn.execute("UPDATE workout SET review_status = 'pending' WHERE id = ?", (workout_id,))
    else:
        conn.execute("UPDATE workout SET review_status = 'ignored' WHERE id = ?", (workout_id,))

    _resync_strap_link(conn, request, workout_id, body.sport if body.action == "classify" else None)
    conn.commit()

    row = conn.execute("SELECT * FROM workout WHERE id = ?", (workout_id,)).fetchone()
    return _serialize_workout(row)


class WorkoutIn(BaseModel):
    start_ts: int
    end_ts: int
    user_sport: str | None = None
    user_title: str | None = None
    notes: str | None = None


@router.post("/api/workouts", status_code=201)
def post_workout(body: WorkoutIn, conn: sqlite3.Connection = Depends(get_conn)):
    """Crea un entreno a mano: el que hiciste sin el reloj puesto.

    ``source='manual'`` no es una etiqueta decorativa, es lo que lo hace
    inmune a la ingesta: el UPSERT de ``_upsert_workouts`` va por
    ``(source, external_id)`` con ``source='zepp'``, así que estas filas no
    entran nunca en ese conflicto. Ningún sync las toca, las pisa ni las borra.

    ``review_status='classified'``: no va a la cola de revisión. La cola existe
    para preguntar "¿qué hiciste aquí?" sobre algo que apareció solo; esto lo
    acabas de escribir tú.
    """
    if body.end_ts < body.start_ts:
        raise HTTPException(status_code=400, detail="'end_ts' debe ser >= 'start_ts'")
    clean = {
        key: (value.strip() or None) if isinstance(value, str) else value
        for key, value in body.model_dump().items()
    }
    cursor = conn.execute(
        "INSERT INTO workout (source, external_id, start_ts, end_ts, user_sport, user_title, "
        "notes, auto_recognized, review_status) VALUES ('manual',NULL,?,?,?,?,?,0,'classified')",
        (clean["start_ts"], clean["end_ts"], clean["user_sport"], clean["user_title"], clean["notes"]),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM workout WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize_workout(row, conn)


@router.delete("/api/workouts/{workout_id}", status_code=204)
def delete_workout(workout_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Borra un entreno MANUAL.

    Solo los manuales, y no por prudencia: borrar uno de Zepp no serviría de
    nada porque el siguiente sync lo volvería a traer. Para esos existe
    descartar (``review_status='ignored'``), que sí sobrevive a la re-ingesta.
    Devolver 409 con esa explicación es más útil que un borrado que se deshace
    solo esa noche.
    """
    row = conn.execute("SELECT source FROM workout WHERE id = ?", (workout_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="workout no encontrado")
    if row["source"] != "manual":
        raise HTTPException(
            status_code=409,
            detail="solo se borran los entrenos manuales; los del reloj se descartan "
            "(volverían en el siguiente sync)",
        )
    conn.execute("DELETE FROM workout_set WHERE workout_id = ?", (workout_id,))
    conn.execute("UPDATE workout SET linked_workout_id = NULL WHERE linked_workout_id = ?", (workout_id,))
    conn.execute("DELETE FROM workout WHERE id = ?", (workout_id,))
    conn.commit()


class WorkoutPatch(BaseModel):
    """Campos editables. Ausente = no se toca; ``null`` = borrar el valor."""

    user_title: str | None = None
    notes: str | None = None
    user_sport: str | None = None


@router.patch("/api/workouts/{workout_id}")
def patch_workout(
    workout_id: int,
    body: WorkoutPatch,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Edita lo que escribe el usuario sobre un entreno.

    Solo toca columnas que la ingesta NO escribe (ver migración 006), así que
    la edición sobrevive a cualquier re-sync. El resto —horas, FC, carga— es
    medición del reloj y no se edita: cambiarla sería inventarse el dato, y la
    siguiente sincronización lo devolvería a su sitio de todas formas.

    Distingue "no lo toques" de "bórralo": un campo ausente del JSON se queda
    como está; mandarlo a ``null`` lo vacía. Sin esa distinción no habría forma
    de quitar una nota sin pisar el título.
    """
    row = conn.execute("SELECT id FROM workout WHERE id = ?", (workout_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="workout no encontrado")

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="nada que actualizar")
    for key in ("user_title", "notes", "user_sport"):
        if isinstance(fields.get(key), str):
            fields[key] = fields[key].strip() or None

    assignments = ", ".join(f"{c} = ?" for c in fields)  # claves validadas por el modelo
    conn.execute(
        f"UPDATE workout SET {assignments} WHERE id = ?", (*fields.values(), workout_id)
    )

    # Reclasificar a fuerza (o dejar de serlo) mueve el vínculo con Hevy igual
    # que hacerlo desde la cola: es la misma decisión por otra puerta.
    if "user_sport" in fields:
        _resync_strap_link(conn, request, workout_id, fields["user_sport"])
    conn.commit()

    row = conn.execute("SELECT * FROM workout WHERE id = ?", (workout_id,)).fetchone()
    return _serialize_workout(row, conn)


# ---------------------------------------------------------------------------
# Sync on-demand: background task + polling (síncrono = timeout)
# ---------------------------------------------------------------------------


def _default_sync_client_factory(config: dict) -> ZeppClient:
    return ZeppClient(ZeppAuth(config), config)


def _run_sync_job(app: FastAPI, config: dict, client_factory: Callable[[dict], Any]) -> None:
    state = app.state
    try:
        client = client_factory(config)
        today = datetime.now(ZoneInfo(config["tz"])).date()
        days = run.build_days(today, days=config["ventana_dias"])
        init_db(state.db_path)
        conn = sqlite3.connect(state.db_path)
        try:
            stats = run.run_ingest(conn, client, days, config, today=today)
        finally:
            conn.close()
        with state.sync_lock:
            state.sync_status = {
                "status": "ok",
                "started_at": state.sync_status["started_at"],
                "finished_at": time.time(),
                "stats": stats,
                "error": None,
            }
    except Exception as exc:  # una ingesta rota no debe tumbar el proceso del backend
        with state.sync_lock:
            state.sync_status = {
                "status": "error",
                "started_at": state.sync_status["started_at"],
                "finished_at": time.time(),
                "stats": None,
                "error": str(exc),
            }


@router.post("/api/sync", status_code=202)
def post_sync(request: Request):
    state = request.app.state
    if state.sync_config is None:
        raise HTTPException(status_code=503, detail=state.sync_off_reason)

    with state.sync_lock:
        if state.sync_status["status"] == "running":
            raise HTTPException(status_code=409, detail="sync ya en curso")
        state.sync_status = {
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "stats": None,
            "error": None,
        }

    # Hilo aparte (no BackgroundTasks de Starlette): debe seguir corriendo
    # aunque la respuesta ya se haya enviado, para que /api/sync/status
    # pueda sondearse en peticiones posteriores independientes.
    thread = threading.Thread(
        target=_run_sync_job,
        args=(request.app, state.sync_config, state.sync_client_factory),
        daemon=True,
    )
    thread.start()
    return state.sync_status


@router.get("/api/sync/status")
def get_sync_status(request: Request):
    return request.app.state.sync_status


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    db_path: Path | str | None = None,
    tz: str = DEFAULT_TZ,
    api_token: str | None = None,
    cors_origins: list[str] | None = None,
    strength_sport: str = hevy.DEFAULT_STRENGTH_SPORT,
    sync_config: dict | None = None,
    sync_off_reason: str = "ingest/config.toml no configurado",
    sync_client_factory: Callable[[dict], Any] = _default_sync_client_factory,
) -> FastAPI:
    app = FastAPI(title="zepp-dashboard API")
    app.state.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    app.state.tz = tz
    app.state.api_token = api_token
    app.state.strength_sport = strength_sport
    app.state.sync_config = sync_config
    app.state.sync_off_reason = sync_off_reason
    app.state.sync_client_factory = sync_client_factory
    app.state.sync_lock = threading.Lock()
    app.state.sync_status = {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "stats": None,
        "error": None,
    }

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else DEFAULT_CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, dependencies=[Depends(require_auth)])

    # La web compilada se sirve desde el MISMO proceso: `npm run build` +
    # `uvicorn backend.api:app` es todo el despliegue, sin servidor estático
    # aparte y sin CORS (mismo origen). Va DESPUÉS del router para que /api/*
    # gane, y `html=True` sirve index.html en la raíz. Un /api/typo sigue
    # devolviendo 404 JSON, no la web (comprobado): StaticFiles solo aplica el
    # index a peticiones de directorio.
    # Sin `frontend/dist/` (nadie ha compilado) no se monta nada: en desarrollo
    # el front lo sirve Vite en :5173 con su proxy a este backend.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


_config = load_config(required=False)
app = create_app(
    db_path=_config.get("db_path"),
    tz=_config.get("tz", DEFAULT_TZ),
    api_token=_config.get("api_token"),
    cors_origins=_config.get("cors_origins"),
    strength_sport=_config.get("strength_sport", hevy.DEFAULT_STRENGTH_SPORT),
    sync_config=_config or None,
)
