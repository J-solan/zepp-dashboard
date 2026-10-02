"""Import de Hevy (fuente de verdad de fuerza) desde el export CSV.

El strap no da el detalle de fuerza: el ejercicio, las reps, el peso y
el músculo salen de aquí, y el workout type-52 del reloj aporta el overlay
fisiológico (FC, carga, zonas, TE). Este módulo importa el CSV y cruza ambos.

Tres subcomandos::

    uv run python -m ingest.hevy clean export.csv [limpio.csv]   # 14 -> 9 columnas
    uv run python -m ingest.hevy import export.csv               # -> workout/workout_set
    uv run python -m ingest.hevy import limpio.csv               # también acepta el limpio

Decisiones que impone el formato del export (ver README de Hevy: Profile →
Settings → Export & Import Data):

- **Las HORAS del CSV no son fiables**, las teclea el usuario al registrar el
  entreno; la FECHA sí. De ahí que el matching con el strap sea por día local y
  que al vincular se adopte la ventana del reloj (ver ``link_to_strap``).
- **Meses en español** ("16 jul 2026, 14:24") con mapa propio: el locale del
  sistema no está garantizado en CI ni en la máquina del usuario.
- **Los pesos ya vienen en kg** (columna ``weight_kg``), no hay conversión.
- **Las series de calentamiento se importan marcadas**, no se descartan:
  ``workout_set.set_type`` guarda el valor verbatim de Hevy ('normal',
  'warmup', 'dropset', 'failure'). Descartarlas perdería series reales y el
  agregado de volumen puede excluirlas con un WHERE.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ingest.config import load_config
from ingest.db import DEFAULT_DB_PATH, init_db

ROOT = Path(__file__).resolve().parent.parent
MUSCLE_MAP_PATH = ROOT / "ingest" / "muscle_map.toml"
DEFAULT_TZ = "Europe/Madrid"

# Nombre del deporte que dispara el vínculo Hevy↔strap. Es un NOMBRE y no el
# code 52 a propósito: así vale tanto para el entreno que el reloj reconoció
# solo como para el 223 que el usuario reclasificó a mano, y quien traduzca
# ``[sport_types]`` en su config solo tiene que cambiar ``strength_sport``.
DEFAULT_STRENGTH_SPORT = "fuerza"

# Las 9 columnas con contenido del export. Las 5 que se tiran son ruido para
# fuerza: description/exercise_notes/superset_id vienen vacías y
# distance_km/duration_seconds solo aplican a cardio.
ESSENTIAL_COLUMNS = [
    "title",
    "start_time",
    "end_time",
    "exercise_title",
    "set_index",
    "set_type",
    "weight_kg",
    "reps",
    "rpe",
]

# Mes -> nº, indexado por las 3 primeras letras: cubre tanto la forma
# abreviada del export ('jul', 'sept') como la larga ('julio', 'septiembre').
_MONTHS = {
    name: number
    for number, name in enumerate(
        ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"], 1
    )
}


# ---------------------------------------------------------------------------
# Parseo del CSV
# ---------------------------------------------------------------------------


def parse_hevy_datetime(text: str, tz: str) -> int:
    """``'16 jul 2026, 14:24'`` → unix s UTC, interpretado en la tz local."""
    date_part, _, time_part = text.partition(",")
    day, month, year = date_part.split()
    hour, minute, *rest = time_part.strip().split(":")

    key = month.lower().rstrip(".")[:3]
    if key not in _MONTHS:
        raise ValueError(f"mes desconocido en la fecha de Hevy: {text!r}")

    stamp = datetime(
        int(year),
        _MONTHS[key],
        int(day),
        int(hour),
        int(minute),
        int(rest[0]) if rest else 0,
        tzinfo=ZoneInfo(tz),
    )
    return int(stamp.timestamp())


def read_rows(csv_path: Path | str) -> list[dict[str, str]]:
    """Filas del CSV, acepte el export original (14 columnas) o el limpio (9).

    La detección es por cabecera: da igual cuántas columnas haya mientras estén
    las 9 esenciales.
    """
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in ESSENTIAL_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{csv_path}: no parece un export de Hevy, faltan columnas: {missing}")
        return [{c: (row[c] or "").strip() for c in ESSENTIAL_COLUMNS} for row in reader]


def _number(value: str, cast: type) -> float | int | None:
    return cast(float(value)) if value else None


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------


def clean(csv_path: Path | str, out_path: Path | str | None = None) -> int:
    """Reescribe el CSV con solo las 9 columnas esenciales. Sin ``out_path``,
    a stdout (así se puede encadenar con otra herramienta)."""
    rows = read_rows(csv_path)
    handle = open(out_path, "w", newline="", encoding="utf-8") if out_path else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=ESSENTIAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if out_path:
            handle.close()
    return len(rows)


# ---------------------------------------------------------------------------
# Mapa de músculos
# ---------------------------------------------------------------------------


def load_muscle_map(path: Path | str = MUSCLE_MAP_PATH) -> dict[str, dict[str, float]]:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def upsert_exercise_muscle(conn: sqlite3.Connection, muscle_map: dict[str, dict[str, float]]) -> None:
    conn.executemany(
        "INSERT INTO exercise_muscle (exercise, muscle, intensity) VALUES (?,?,?) "
        "ON CONFLICT(exercise, muscle) DO UPDATE SET intensity=excluded.intensity",
        [
            (exercise, muscle, intensity)
            for exercise, muscles in muscle_map.items()
            for muscle, intensity in muscles.items()
        ],
    )


def primary_muscle(muscles: dict[str, float]) -> str:
    """El músculo de intensidad 1.0, que es lo que espera
    ``workout_set.muscle_group`` (una sola etiqueta, esquema de la 001).

    Se toma el de intensidad máxima: con un mapa bien formado es el 1.0, y si
    hubiera empate gana el primero declarado en el TOML (orden estable).
    """
    return max(muscles, key=muscles.get)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def _external_id(title: str, start_time: str) -> str:
    """Hash de title+start_time: el export no trae id de workout y el par
    (título, inicio) es lo único estable entre dos exports."""
    return hashlib.sha256(f"{title}|{start_time}".encode()).hexdigest()[:16]


def import_csv(
    conn: sqlite3.Connection,
    csv_path: Path | str,
    tz: str = DEFAULT_TZ,
    muscle_map: dict[str, dict[str, float]] | None = None,
    strength_sport: str = DEFAULT_STRENGTH_SPORT,
) -> dict:
    """Importa el CSV a ``workout``/``workout_set`` y vincula con el strap.

    Idempotente: UPSERT del workout por (source, external_id) y DELETE+INSERT
    de sus series, así que re-importar el mismo CSV no duplica nada.
    """
    muscle_map = load_muscle_map() if muscle_map is None else muscle_map
    upsert_exercise_muscle(conn, muscle_map)

    workouts: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in read_rows(csv_path):
        workouts.setdefault((row["title"], row["start_time"]), []).append(row)

    unmapped: set[str] = set()
    n_sets = 0

    for (title, start_time), rows in workouts.items():
        external_id = _external_id(title, start_time)
        # linked_workout_id se resetea en cada import: lo re-decide el matching
        # de más abajo con los datos que haya ahora en la tabla.
        conn.execute(
            "INSERT INTO workout (source, external_id, sport, title, start_ts, end_ts, linked_workout_id) "
            "VALUES ('hevy',?,?,?,?,?,NULL) "
            "ON CONFLICT(source, external_id) DO UPDATE SET start_ts=excluded.start_ts, "
            "end_ts=excluded.end_ts, sport=excluded.sport, title=excluded.title, linked_workout_id=NULL",
            (
                external_id,
                strength_sport,
                title,
                parse_hevy_datetime(start_time, tz),
                parse_hevy_datetime(rows[0]["end_time"], tz),
            ),
        )
        workout_id = conn.execute(
            "SELECT id FROM workout WHERE source='hevy' AND external_id=?", (external_id,)
        ).fetchone()[0]

        conn.execute("DELETE FROM workout_set WHERE workout_id=?", (workout_id,))
        for row in rows:
            exercise = row["exercise_title"]
            muscles = muscle_map.get(exercise)
            if muscles is None:
                unmapped.add(exercise)
            conn.execute(
                "INSERT INTO workout_set (workout_id, exercise, muscle_group, set_index, "
                "reps, weight_kg, rpe, set_type) VALUES (?,?,?,?,?,?,?,?)",
                (
                    workout_id,
                    exercise,
                    primary_muscle(muscles) if muscles else None,
                    _number(row["set_index"], int),
                    _number(row["reps"], int),
                    _number(row["weight_kg"], float),
                    _number(row["rpe"], float),
                    row["set_type"] or None,
                ),
            )
            n_sets += 1

    linked, ambiguous = link_to_strap(conn, tz, strength_sport)
    conn.commit()

    return {
        "workouts": len(workouts),
        "sets": n_sets,
        "linked": linked,
        "ambiguous": ambiguous,
        "unmapped": sorted(unmapped),
    }


# ---------------------------------------------------------------------------
# Matching hevy <-> strap
# ---------------------------------------------------------------------------


def _local_day(ts: int, tz: str) -> str:
    return datetime.fromtimestamp(ts, ZoneInfo(tz)).date().isoformat()


def link_to_strap(
    conn: sqlite3.Connection, tz: str = DEFAULT_TZ, strength_sport: str = DEFAULT_STRENGTH_SPORT
) -> tuple[int, list[tuple[str, int]]]:
    """Vincula cada workout de Hevy con el entreno de fuerza del strap del MISMO día local.

    "De fuerza" son dos cosas: el entreno que el **reloj reconoció solo** (su
    ``sport`` sale del mapa ``[sport_types]`` del config, code 52 en el Helio
    Strap) y el **auto-detectado que el usuario reclasificó** en la cola de
    revisión (``user_sport``). Los dos casos comparten regla a propósito: si el
    usuario olvidó arrancar el tracking, ese auto-detectado es el mismo entreno
    y merece el mismo vínculo (``POST /api/workouts/{id}/review``).

    El filtro es por **nombre** (``strength_sport``) y no por el code numérico:
    otro dispositivo Amazfit puede usar otro code, y así basta con que el
    ``[sport_types]`` de cada uno lo traduzca a este nombre.

    El cruce es **por fecha, no por ventana temporal** (corrige el "±15 min" que
    se propuso al principio): las horas del CSV las teclea el usuario y
    pueden estar desviadas una hora entera, mientras que la fecha sí es fiable y
    el usuario hace como mucho **un entreno de fuerza al día**.

    Regla:

    - **Exactamente 1 candidato** → se guarda ``linked_workout_id`` y los
      ``start_ts``/``end_ts`` del workout de Hevy se **sobreescriben** con los
      del strap: la ventana del reloj es la hora oficial, la del CSV es manual.
      Sin esto, el overlay de FC se pintaría desplazado.
    - **0 o >1 candidatos** → sin vínculo, y el día se devuelve en la lista de
      avisos para que el usuario lo resuelva a mano (re-vinculación manual en la
      UI, pendiente).

    Devuelve ``(vinculados, [(día, nº candidatos), ...])``.
    """
    strap_days: dict[str, list[tuple[int, int, int]]] = {}
    for row in conn.execute(
        "SELECT id, start_ts, end_ts FROM workout "
        "WHERE source='zepp' AND (sport=? OR user_sport=?) AND start_ts IS NOT NULL",
        (strength_sport, strength_sport),
    ):
        strap_days.setdefault(_local_day(row[1], tz), []).append(row)

    linked = 0
    ambiguous: list[tuple[str, int]] = []
    for hevy_id, start_ts in conn.execute(
        "SELECT id, start_ts FROM workout WHERE source='hevy' AND start_ts IS NOT NULL"
    ).fetchall():
        day = _local_day(start_ts, tz)
        candidates = strap_days.get(day, [])
        if len(candidates) != 1:
            ambiguous.append((day, len(candidates)))
            continue
        strap_id, strap_start, strap_end = candidates[0]
        conn.execute(
            "UPDATE workout SET linked_workout_id=?, start_ts=?, end_ts=? WHERE id=?",
            (strap_id, strap_start, strap_end, hevy_id),
        )
        linked += 1

    return linked, ambiguous


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Import del export CSV de Hevy.")
    sub = parser.add_subparsers(dest="command", required=True)

    clean_cmd = sub.add_parser("clean", help="reduce el CSV a las 9 columnas esenciales")
    clean_cmd.add_argument("csv")
    clean_cmd.add_argument("out", nargs="?", help="destino; por defecto stdout")

    import_cmd = sub.add_parser("import", help="importa el CSV (original o limpio) a la BBDD")
    import_cmd.add_argument("csv")
    import_cmd.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)
    import_cmd.add_argument("--tz", default=None)

    args = parser.parse_args(argv)

    if args.command == "clean":
        rows = clean(args.csv, args.out)
        if args.out:
            print(f"{rows} filas escritas en {args.out}")
        return

    config = load_config(required=False)
    init_db(args.db)
    conn = sqlite3.connect(args.db)
    try:
        stats = import_csv(
            conn,
            args.csv,
            args.tz or config.get("tz", DEFAULT_TZ),
            strength_sport=config.get("strength_sport", DEFAULT_STRENGTH_SPORT),
        )
    finally:
        conn.close()

    print(f"workouts: {stats['workouts']}  series: {stats['sets']}  vinculados: {stats['linked']}")
    for day, count in stats["ambiguous"]:
        motivo = "sin fuerza del strap" if count == 0 else f"{count} candidatos del strap"
        print(f"AVISO: {day} sin vincular ({motivo})")
    if stats["unmapped"]:
        print(f"WARN: {len(stats['unmapped'])} ejercicios sin mapear en muscle_map.toml:")
        for exercise in stats["unmapped"]:
            print(f"  - {exercise}")


if __name__ == "__main__":
    main()
