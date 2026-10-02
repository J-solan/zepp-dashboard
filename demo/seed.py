"""BBDD de demostración: 90 días inventados que terminan hoy.

Nada sale de una cuenta real: todo lo genera un ``random.Random`` con semilla
fija, así que el mismo ``today`` da siempre los mismos datos. Se escribe sobre
las migraciones reales (``init_db``) y la fuerza entra por
``hevy.import_csv``, el mismo camino que un export de verdad: el reparto por
músculo y el vínculo con el strap los hace el código de producción.

Lo raro está a propósito, para que la demo enseñe cómo lo pinta la app:

- días sin pulsera (ni una fila de nada: un hueco es un hueco) y noches con la
  pulsera cargando (sin sueño ni FC esa noche);
- una semana mala: más estrés, peor sueño y readiness;
- cola de revisión con auto-detectados pendientes, uno de ellos un día de
  fuerza que el reloj no reconoció (con su entreno de Hevy como pista) y otro
  con un sport code que el config no conoce.

Uso: ``uv run python -m demo`` (ver ``demo/__main__.py``).
"""

from __future__ import annotations

import bisect
import csv
import math
import random
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ingest import hevy, run
from ingest.db import init_db

DEFAULT_TZ = hevy.DEFAULT_TZ
DAYS = 90
SEED = 20260101

# Los tres codes de ``ingest/config.example.toml``. El 999 no está en ese mapa
# a propósito: es el "sport code desconocido" que acaba en la cola.
SPORTS = {52: "fuerza", 122: "voley_playa", 223: "auto_ia"}
STRENGTH, VOLLEY, AUTO, UNKNOWN_CODE = 52, 122, 223, 999

MAX_HR = 188
# Techo de cada zona (50-100 % de la FC máx.), en el formato de ``heart_range``:
# ver docs/zepp-api.md, "Workouts".
ZONE_CEILINGS = [round(MAX_HR * pct / 100) for pct in (50, 60, 70, 80, 90, 100)]

# Rutinas inventadas sobre ejercicios de ``ingest/muscle_map.toml`` (uno que no
# estuviera ahí se importaría sin músculo, y el test lo pilla). El número es el
# peso de partida en kg; sube un 15 % a lo largo del periodo.
ROUTINES = {
    "Torso 💪": [
        ("Press de Banca Inclinado (Mancuerna)", 18),
        ("Jalón al Pecho (Cable)", 45),
        ("Remo Sentado con Cable", 40),
        ("Elevacion Laterales (Mancuerna)", 7),
        ("Tríceps con Polea", 20),
        ("Curl de Bíceps Inclinado (Mancuerna)", 10),
    ],
    "Pierna 💪": [
        ("Sentadilla (Barra)", 50),
        ("Peso Muerto Rumano (Barra)", 45),
        ("Press de Piernas", 100),
        ("Curl de Piernas Acostado (Máquina)", 30),
        ("Extensión de Pierna", 35),
        ("Impulso de Cadera (Máquina)", 60),
    ],
}
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]


@dataclass
class _Workout:
    code: int
    start: int
    end: int
    effort: float  # 0-1: cuánto sube la FC sobre la de reposo
    review: str = "auto"
    user_sport: str | None = None
    lifting: bool = False  # hubo pesas: genera su entreno de Hevy


def _local_ts(day: date, hour: int, minute: int, zone: ZoneInfo) -> int:
    return int(datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone).timestamp())


def _night(rng: random.Random, bed: int, wake: int, bad: bool) -> list[tuple[int, int, int]]:
    """Fases contiguas de ``bed`` a ``wake`` en ciclos de ~90 min: ligero,
    profundo (menguante), ligero, REM (creciente) y a veces un despertar.
    Códigos de ``sleep_stage``: 4 ligero, 5 profundo, 7 despierto, 8 REM."""
    stages: list[tuple[int, int, int]] = []
    t, cycle = bed, 0
    while t < wake:
        deep = max(4, (18 if bad else 30) - cycle * 6 + rng.randint(-4, 4))
        steps = [(4, rng.randint(12, 25)), (5, deep), (4, rng.randint(8, 18)), (8, 8 + cycle * 6 + rng.randint(-3, 6))]
        if rng.random() < (0.5 if bad else 0.25):
            steps.append((7, rng.randint(2, 6)))
        for stage, minutes in steps:
            end = min(t + minutes * 60, wake)
            if end > t:
                stages.append((t, end, stage))
            t = end
        cycle += 1
    return stages


def _heart_range(bpms: list[int]) -> str:
    """Segundos por zona: ``'s,techo;s,techo;...'``, como lo manda el reloj."""
    seconds = [0] * len(ZONE_CEILINGS)
    for bpm in bpms:
        zone = next((k for k, ceiling in enumerate(ZONE_CEILINGS) if bpm <= ceiling), len(ZONE_CEILINGS) - 1)
        seconds[zone] += 60
    return ";".join(f"{s},{c}" for s, c in zip(seconds, ZONE_CEILINGS))


def _hevy_time(ts: int, zone: ZoneInfo) -> str:
    """Formato del export de Hevy: ``'16 jul 2026, 14:24'``."""
    local = datetime.fromtimestamp(ts, zone)
    return f"{local.day} {_MESES[local.month - 1]} {local.year}, {local:%H:%M}"


def build(
    db_path: Path | str,
    today: date,
    *,
    until: int,
    tz: str = DEFAULT_TZ,
    days: int = DAYS,
    seed: int = SEED,
) -> None:
    """Crea la demo en ``db_path``, que no debe existir.

    ``until`` (unix s) es "ahora": lo posterior no se escribe, igual que una
    pulsera que aún no ha sincronizado el resto del día. El azar NO depende de
    ``until`` (se sortea todo y se filtra al final), así que el mismo ``today``
    da los mismos datos a cualquier hora.
    """
    rng = random.Random(seed)
    zone = ZoneInfo(tz)
    dates = [today - timedelta(days=days - 1 - i) for i in range(days)]
    # Medianoches locales: con cambio de hora un día dura 23 o 25 h.
    bounds = [_local_ts(d, 0, 0, zone) for d in dates] + [_local_ts(today + timedelta(days=1), 0, 0, zone)]
    origin, n = bounds[0], (bounds[-1] - bounds[0]) // 60

    # Huecos y semana mala fuera de la última semana: la vista con la que abre
    # la web tiene que salir completa.
    quiet = range(days - 7)
    off_days = set(rng.sample(quiet, 5))
    charging = set(rng.sample([i for i in quiet if i not in off_days], 4))
    bad_week = set(range(days - 21, days - 14))
    rest_hr = [51 + (4 if i in bad_week else 0) + rng.gauss(0, 1.5) for i in range(days)]

    # Línea de tiempo por minuto desde la primera medianoche.
    sleep_stage = bytearray(n)  # fase del minuto (0 = despierto)
    strap_off = bytearray(n)
    effort = [0.0] * n

    def mark(start: int, end: int, array, value) -> None:
        for m in range(max(0, (start - origin) // 60), min(n, (end - origin) // 60)):
            array[m] = value

    # --- Plan: noches y entrenos -------------------------------------------
    nights: dict[int, tuple[list[tuple[int, int, int]], dict[int, int], int]] = {}
    workouts: list[_Workout] = []
    for i, d in enumerate(dates):
        bad = i in bad_week
        if i in off_days:
            mark(_local_ts(d - timedelta(days=1), 23, 0, zone), bounds[i + 1], strap_off, 1)
            continue
        if i in charging:
            mark(_local_ts(d - timedelta(days=1), 23, 0, zone), _local_ts(d, 7, 30, zone), strap_off, 1)
        else:
            # Tras un día sin pulsera se la vuelve a poner pasada la medianoche.
            if i - 1 in off_days:
                bed = _local_ts(d, 0, 15, zone)
            else:
                bed = _local_ts(d - timedelta(days=1), 23, 0, zone)
            bed += rng.randint(0, 75) * 60 + (30 * 60 if bad else 0)
            wake = _local_ts(d, 6, 45, zone) + rng.randint(0, 60) * 60 + (50 * 60 if d.weekday() >= 5 else 0)
            stages = _night(rng, bed, wake, bad)
            minutes = {s: sum((e - b) // 60 for b, e, st in stages if st == s) for s in (4, 5, 7, 8)}
            total = (stages[-1][1] - stages[0][0]) // 60
            score = round(min(98, max(30, 40 + (total - 300) * 0.12 + minutes[5] * 0.25 - minutes[7] * 0.5 + rng.gauss(0, 3))))
            nights[i] = (stages, minutes, score)
            for start, end, stage in stages:
                mark(start, end, sleep_stage, stage)

        if d.weekday() in (0, 3):  # lunes y jueves, pesas por la tarde
            start = _local_ts(d, 18, 30, zone) + rng.randint(-20, 30) * 60
            workouts.append(_Workout(STRENGTH, start, start + rng.randint(55, 75) * 60, rng.uniform(0.25, 0.4), lifting=True))
        if d.weekday() == 5 and d.isocalendar().week % 2 == 0:  # vóley, sábados alternos
            start = _local_ts(d, 11, 0, zone) + rng.randint(0, 30) * 60
            workouts.append(_Workout(VOLLEY, start, start + rng.randint(80, 110) * 60, rng.uniform(0.6, 0.8)))
        elif rng.random() < 0.35:  # lo que el reloj detecta solo: paseo, bici...
            start = _local_ts(d, rng.randint(8, 16), rng.randint(0, 59), zone)
            workouts.append(_Workout(AUTO, start, start + rng.randint(15, 40) * 60, rng.uniform(0.3, 0.5), review="pending"))
        if i == days - 4:  # algo que el config no sabe nombrar
            start = _local_ts(d, 20, 30, zone)
            workouts.append(_Workout(UNKNOWN_CODE, start, start + 50 * 60, 0.55, review="pending"))

    # Lo antiguo ya está revisado; los tres últimos auto-detectados antes de hoy
    # (y los de hoy) esperan en la cola.
    today_start = bounds[-2]
    autos = [w for w in workouts if w.code == AUTO and w.end <= today_start]
    for w in autos[:-3]:
        w.review, w.user_sport = rng.choice([("classified", "bici"), ("classified", "caminar"), ("ignored", None)])
    # Un día de pesas que el reloj tomó por auto-detectado: su Hevy queda sin
    # vincular y es la pista que muestra la cola.
    missed = [w for w in workouts if w.code == STRENGTH and w.end <= today_start][-2]
    missed.code, missed.review = AUTO, "pending"

    for w in workouts:
        mark(w.start, w.end, effort, w.effort)

    # --- Series por minuto -------------------------------------------------
    hr: list[tuple[int, int]] = []
    stress: list[tuple[int, int]] = []
    charge: list[tuple[int, int, float, float, int]] = []
    stress_by_day: dict[int, list[int]] = defaultdict(list)
    level, dropout, day = 60.0, 0, 0
    for m in range(n):
        ts = origin + m * 60
        while ts >= bounds[day + 1]:
            day += 1
        if strap_off[m]:
            continue
        rest, bad, stage = rest_hr[day], day in bad_week, sleep_stage[m]
        hour = (ts - bounds[day]) / 3600
        daylight = max(0.0, math.sin(math.pi * (hour - 7) / 16))  # 0 a las 7 y a las 23, 1 a las 15
        if stage:
            level += 0.08 if bad else 0.13
            bpm = rest + {5: -3, 4: 0, 8: 5, 7: 9}[stage] + rng.gauss(0, 1.5)
            value = 12 + rng.gauss(0, 3)
        elif effort[m]:
            level -= 0.25 * effort[m]
            bpm = rest + 35 + effort[m] * 95 + rng.gauss(0, 6)
            value = 45 + effort[m] * 15 + rng.gauss(0, 5)
        else:
            level -= 0.05
            bpm = rest + 14 + 10 * daylight + rng.gauss(0, 4)
            value = 22 + 10 * daylight + (12 if bad else 0) + rng.gauss(0, 6)
        level = min(98.0, max(5.0, level))
        charge.append(
            (
                ts,
                round(level),
                round(min(100.0, max(0.0, level - 9 + rng.gauss(0, 1.5))), 4),
                round(min(100.0, max(0.0, level + 8 + rng.gauss(0, 1.5))), 4),
                0,
            )
        )
        if dropout:  # la pulsera pierde contacto unos minutos: hueco en la FC
            dropout -= 1
        elif not stage and rng.random() < 0.004:
            dropout = rng.randint(3, 15)
        else:
            hr.append((ts, int(min(200, max(38, bpm)))))
        if m % 5 == 0 and (stage or rng.random() > 0.2):
            sample = int(min(99, max(1, value)))
            stress.append((ts, sample))
            if ts < until:
                stress_by_day[day].append(sample)

    # --- Filas derivadas (todo el azar se sortea antes de filtrar) ----------
    hr_by_ts = dict(hr)
    workout_rows = []
    load_by_day: dict[int, int] = defaultdict(int)
    for w in workouts:
        bpms = [hr_by_ts[t] for t in range(w.start, w.end, 60) if t in hr_by_ts]
        load = round((w.end - w.start) / 60 * (0.2 + w.effort * 1.6))
        te = round(min(5.0, max(0.5, 0.8 + w.effort * 3.2 + rng.gauss(0, 0.3))), 1)
        if w.end > until:
            continue
        load_by_day[bisect.bisect_right(bounds, w.start) - 1] += load
        workout_rows.append(
            (
                str(w.start),
                SPORTS.get(w.code),
                w.code,
                w.start,
                w.end,
                load,
                te,
                round(sum(bpms) / len(bpms)) if bpms else None,
                max(bpms) if bpms else None,
                _heart_range(bpms),
                1 if w.code == AUTO else 0,
                w.review,
                w.user_sport,
            )
        )

    daily_rows = []
    for i, d in enumerate(dates):
        steps = rng.randint(5500, 11000) - (2500 if i in bad_week else 0)
        hrv = 85 + rng.gauss(0, 9) - (25 if i in bad_week else 0)
        resp = 16.4 + rng.gauss(0, 0.4) + (0.6 if i in bad_week else 0)
        noise = rng.gauss(0, 3)
        if i in off_days or until <= bounds[i]:
            continue
        frac = min(1.0, (until - bounds[i]) / (bounds[i + 1] - bounds[i]))  # hoy va a medias
        steps = round((steps + (2500 if load_by_day[i] else 0)) * frac)
        night = nights.get(i)
        slept = night is not None and night[0][-1][1] <= until
        samples = stress_by_day[i]
        daily_rows.append(
            (
                d.isoformat(),
                steps,
                round(steps * 0.045 + load_by_day[i] * 4),
                round(rest_hr[i]) if slept else None,
                round(min(98, max(30, 35 + night[2] * 0.5 + (hrv - 70) * 0.3 + noise))) if slept else None,
                round(hrv) if slept else None,
                round(resp, 1) if slept else None,
                round(sum(samples) / len(samples)) if samples else None,
                load_by_day[i],
                tz,
            )
        )

    hevy_rows = []
    for k, w in enumerate(w for w in workouts if w.lifting):
        title = list(ROUTINES)[k % 2]
        progress = (w.start - origin) / (bounds[-1] - origin)
        typed_start = w.start + rng.randint(-20, 20) * 60  # la hora del CSV se teclea a mano
        typed_end = typed_start + (w.end - w.start) + rng.randint(-10, 10) * 60
        sets = []
        for j, (exercise, base_kg) in enumerate(ROUTINES[title]):
            kg = base_kg * (1 + 0.15 * progress)
            plan = ([("warmup", kg * 0.5)] if j == 0 else []) + [("normal", kg)] * 3
            for index, (set_type, weight) in enumerate(plan):
                sets.append(
                    {
                        "title": title,
                        "start_time": _hevy_time(typed_start, zone),
                        "end_time": _hevy_time(typed_end, zone),
                        "exercise_title": exercise,
                        "set_index": index,
                        "set_type": set_type,
                        "weight_kg": f"{round(weight * 2) / 2:g}",
                        "reps": rng.randint(8, 12),
                        "rpe": "",
                    }
                )
        if w.end <= until:
            hevy_rows.extend(sets)

    sources = [s for s, *_ in run.PER_DAY_SOURCES] + [s for s, *_ in run.WINDOW_SOURCES]

    # --- Escritura ---------------------------------------------------------
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany("INSERT INTO hr_minute (ts, bpm) VALUES (?,?)", [r for r in hr if r[0] < until])
        conn.executemany("INSERT INTO stress_sample (ts, value) VALUES (?,?)", [r for r in stress if r[0] < until])
        conn.executemany(
            "INSERT INTO biocharge (ts, total, mental, physical, status) VALUES (?,?,?,?,?)",
            [r for r in charge if r[0] < until],
        )
        for i, (stages, minutes, score) in nights.items():
            if stages[-1][1] > until:
                continue
            cursor = conn.execute(
                "INSERT INTO sleep_session (day, start_ts, end_ts, score, deep_min, light_min, rem_min, "
                "awake_min, wake_count, resting_hr, tz, is_nap) VALUES (?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    dates[i].isoformat(),
                    stages[0][0],
                    stages[-1][1],
                    score,
                    minutes[5],
                    minutes[4],
                    minutes[8],
                    minutes[7],
                    sum(1 for *_, st in stages if st == 7),
                    round(rest_hr[i]),
                    tz,
                ),
            )
            conn.executemany(
                "INSERT INTO sleep_stage (session_id, start_ts, end_ts, stage) VALUES (?,?,?,?)",
                [(cursor.lastrowid, *s) for s in stages],
            )
        conn.executemany(
            "INSERT INTO workout (source, external_id, sport, sport_type, start_ts, end_ts, train_load, te, "
            "avg_hr, max_hr, hr_zones, auto_recognized, review_status, user_sport) "
            "VALUES ('zepp',?,?,?,?,?,?,?,?,?,?,?,?,?)",
            workout_rows,
        )
        conn.executemany(
            "INSERT INTO daily_metrics (day, steps, calories, resting_hr, readiness, hrv_ms, "
            "respiratory_rate, stress_avg, vo2max, train_load, tz) VALUES (?,?,?,?,?,?,?,?,NULL,?,?)",
            daily_rows,
        )
        # Un sync 'ok' cada día, también los días sin pulsera: el sync fue
        # bien, la pulsera no estaba puesta.
        conn.executemany(
            "INSERT INTO sync_state (source, day, last_ok_at, status) VALUES (?,?,?,'ok')",
            [(source, d.isoformat(), until) for d in dates for source in sources],
        )
        conn.commit()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "hevy.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=hevy.ESSENTIAL_COLUMNS)
                writer.writeheader()
                writer.writerows(hevy_rows)
            hevy.import_csv(conn, csv_path, tz)
    finally:
        conn.close()
