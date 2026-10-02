"""Tests de ``ingest.hevy``: import del export CSV y cruce con el strap.

Corren sobre ``fixtures/hevy_export.csv`` (sanitizada: los ejercicios son los
reales, los pesos/reps/fechas están perturbados). El lado Zepp se inserta a
mano en cada test — el matching depende de qué type-52 haya ese día, y eso es
justo lo que cada caso quiere controlar.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ingest import db, hevy

FIXTURE = Path(__file__).parent / "fixtures" / "hevy_export.csv"
MIGRATIONS_DIR = Path(hevy.__file__).resolve().parent.parent / "db" / "migrations"
TZ = "Europe/Madrid"

# Días locales de los 3 workouts de la fixture.
FIXTURE_DAYS = ["2006-07-13", "2006-07-18", "2006-07-21"]


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "zepp.db"
    db.init_db(db_path)
    connection = sqlite3.connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def export() -> Path:
    if not FIXTURE.exists():
        pytest.skip("hevy_export.csv no disponible en fixtures/ — se omite")
    return FIXTURE


# Mismo mapa que el ``[sport_types]`` del config: la ingesta real escribe la
# columna ``sport`` traduciendo el code con él, y el matching filtra por ese
# nombre. El helper tiene que hacer lo mismo o probaría algo que no pasa.
SPORT_TYPES = {52: "fuerza", 122: "voley_playa", 223: "auto_ia"}


def add_strap_workout(conn: sqlite3.Connection, day: str, hour: int, *, sport_type: int = 52) -> int:
    """Inserta un workout del strap ese día local, con ventana de 1 h."""
    start = int(datetime.fromisoformat(f"{day}T{hour:02d}:00").replace(tzinfo=ZoneInfo(TZ)).timestamp())
    cur = conn.execute(
        "INSERT INTO workout (source, external_id, sport, sport_type, start_ts, end_ts) "
        "VALUES ('zepp',?,?,?,?,?)",
        (f"strap-{day}-{hour}", SPORT_TYPES.get(sport_type), sport_type, start, start + 3600),
    )
    return cur.lastrowid


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or hevy.ESSENTIAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def base_row(**overrides) -> dict:
    row = {
        "title": "Entreno",
        "start_time": "3 mar 2026, 10:00",
        "end_time": "3 mar 2026, 11:00",
        "exercise_title": "Extensión de Pierna",
        "set_index": "0",
        "set_type": "normal",
        "weight_kg": "70",
        "reps": "20",
        "rpe": "",
    }
    return {**row, **overrides}


# ---------------------------------------------------------------------------
# Fechas en español
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("16 jul 2026, 14:24", "2026-07-16 14:24"),
        ("8 jul 2026, 16:28", "2026-07-08 16:28"),  # día sin cero a la izquierda
        ("1 ene 2026, 00:05", "2026-01-01 00:05"),
        ("28 feb 2026, 23:59", "2026-02-28 23:59"),
        ("9 sept 2026, 07:30", "2026-09-09 07:30"),  # abreviatura de 4 letras
        ("9 sep 2026, 07:30", "2026-09-09 07:30"),
        ("9 septiembre 2026, 07:30", "2026-09-09 07:30"),  # nombre completo
        ("31 dic 2026, 18:00", "2026-12-31 18:00"),
    ],
)
def test_spanish_dates_parse_without_system_locale(text, expected):
    ts = hevy.parse_hevy_datetime(text, TZ)
    assert datetime.fromtimestamp(ts, ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M") == expected


def test_unknown_month_is_rejected_instead_of_guessing():
    with pytest.raises(ValueError, match="mes desconocido"):
        hevy.parse_hevy_datetime("16 xxx 2026, 14:24", TZ)


def test_dates_are_read_in_local_time_not_utc():
    """Julio en Madrid es UTC+2: si se leyera como UTC el día podría bailar."""
    ts = hevy.parse_hevy_datetime("16 jul 2026, 00:30", TZ)
    assert datetime.fromtimestamp(ts, ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M") == "2026-07-15 22:30"


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------


def test_clean_keeps_exactly_the_nine_essential_columns(export, tmp_path):
    out = tmp_path / "limpio.csv"
    hevy.clean(export, out)

    with open(out, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [
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
        rows = list(reader)

    with open(export, newline="", encoding="utf-8") as handle:
        original = list(csv.DictReader(handle))

    assert len(rows) == len(original)
    assert [r["exercise_title"] for r in rows] == [r["exercise_title"] for r in original]


def test_clean_is_idempotent_over_an_already_clean_csv(export, tmp_path):
    once, twice = tmp_path / "1.csv", tmp_path / "2.csv"
    hevy.clean(export, once)
    hevy.clean(once, twice)
    assert twice.read_text(encoding="utf-8") == once.read_text(encoding="utf-8")


def test_clean_writes_to_stdout_when_no_destination(export, capsys):
    hevy.clean(export)
    assert capsys.readouterr().out.splitlines()[0] == ",".join(hevy.ESSENTIAL_COLUMNS)


def test_a_csv_without_the_essential_columns_is_rejected(tmp_path):
    path = tmp_path / "otro.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="faltan columnas"):
        hevy.read_rows(path)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def test_import_creates_one_workout_per_session_with_all_its_sets(conn, export):
    stats = hevy.import_csv(conn, export, TZ)

    assert stats["workouts"] == 3
    assert stats["sets"] == 35
    assert conn.execute("SELECT COUNT(*) FROM workout WHERE source='hevy'").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM workout_set").fetchone()[0] == 35
    assert conn.execute(
        "SELECT DISTINCT sport FROM workout WHERE source='hevy'"
    ).fetchall() == [("fuerza",)]


def test_import_accepts_both_the_original_and_the_cleaned_csv(conn, export, tmp_path):
    cleaned = tmp_path / "limpio.csv"
    hevy.clean(export, cleaned)

    from_original = hevy.import_csv(conn, export, TZ)
    rows_original = conn.execute(
        "SELECT exercise, set_index, reps, weight_kg, set_type FROM workout_set ORDER BY id"
    ).fetchall()

    from_clean = hevy.import_csv(conn, cleaned, TZ)
    rows_clean = conn.execute(
        "SELECT exercise, set_index, reps, weight_kg, set_type FROM workout_set ORDER BY id"
    ).fetchall()

    assert from_original["workouts"] == from_clean["workouts"]
    assert rows_original == rows_clean


def test_set_values_land_in_their_own_columns(conn, tmp_path):
    csv_path = write_csv(
        tmp_path / "in.csv",
        [base_row(set_index="0", weight_kg="82.5", reps="12", rpe="8.5")],
    )
    hevy.import_csv(conn, csv_path, TZ)

    assert conn.execute(
        "SELECT exercise, set_index, reps, weight_kg, rpe FROM workout_set"
    ).fetchone() == ("Extensión de Pierna", 0, 12, 82.5, 8.5)


def test_empty_rpe_is_null_not_zero(conn, tmp_path):
    csv_path = write_csv(tmp_path / "in.csv", [base_row(rpe="")])
    hevy.import_csv(conn, csv_path, TZ)
    assert conn.execute("SELECT rpe FROM workout_set").fetchone() == (None,)


def test_warmup_sets_are_imported_and_marked(conn, tmp_path):
    csv_path = write_csv(
        tmp_path / "in.csv",
        [
            base_row(set_index="0", set_type="warmup", weight_kg="20", reps="15"),
            base_row(set_index="1", set_type="normal", weight_kg="70", reps="12"),
        ],
    )
    hevy.import_csv(conn, csv_path, TZ)

    assert conn.execute(
        "SELECT set_index, set_type FROM workout_set ORDER BY set_index"
    ).fetchall() == [(0, "warmup"), (1, "normal")]


def test_workout_start_and_end_come_from_the_csv_when_there_is_no_strap_session(conn, tmp_path):
    csv_path = write_csv(tmp_path / "in.csv", [base_row()])
    hevy.import_csv(conn, csv_path, TZ)

    start_ts, end_ts = conn.execute("SELECT start_ts, end_ts FROM workout").fetchone()
    assert start_ts == hevy.parse_hevy_datetime("3 mar 2026, 10:00", TZ)
    assert end_ts == hevy.parse_hevy_datetime("3 mar 2026, 11:00", TZ)


# ---------------------------------------------------------------------------
# Idempotencia
# ---------------------------------------------------------------------------


def test_reimporting_the_same_csv_does_not_duplicate_anything(conn, export):
    hevy.import_csv(conn, export, TZ)
    before = conn.execute("SELECT id, external_id, start_ts FROM workout ORDER BY id").fetchall()

    hevy.import_csv(conn, export, TZ)

    assert conn.execute("SELECT COUNT(*) FROM workout").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM workout_set").fetchone()[0] == 35
    assert conn.execute("SELECT id, external_id, start_ts FROM workout ORDER BY id").fetchall() == before


def test_reimport_replaces_the_sets_of_a_workout_instead_of_appending(conn, tmp_path):
    csv_path = write_csv(tmp_path / "in.csv", [base_row(set_index="0"), base_row(set_index="1")])
    hevy.import_csv(conn, csv_path, TZ)

    # Mismo (title, start_time) pero una serie menos: la que sobra debe irse.
    write_csv(csv_path, [base_row(set_index="0", reps="99")])
    hevy.import_csv(conn, csv_path, TZ)

    assert conn.execute("SELECT set_index, reps FROM workout_set").fetchall() == [(0, 99)]


def test_external_id_is_stable_across_imports(conn, export):
    hevy.import_csv(conn, export, TZ)
    ids = conn.execute("SELECT external_id FROM workout ORDER BY external_id").fetchall()
    hevy.import_csv(conn, export, TZ)
    assert conn.execute("SELECT external_id FROM workout ORDER BY external_id").fetchall() == ids


# ---------------------------------------------------------------------------
# exercise_muscle y muscle_group
# ---------------------------------------------------------------------------


def test_muscle_map_covers_every_exercise_of_the_real_export(export):
    """Con el export real no debe quedar ningún ejercicio sin mapear."""
    exercises = {row["exercise_title"] for row in hevy.read_rows(export)}
    assert exercises - set(hevy.load_muscle_map()) == set()


def test_every_mapped_exercise_has_exactly_one_primary_muscle():
    for exercise, muscles in hevy.load_muscle_map().items():
        assert [m for m, i in muscles.items() if i == 1.0], f"{exercise} sin músculo a 1.0"
        assert len([m for m, i in muscles.items() if i == 1.0]) == 1, f"{exercise} con varios 1.0"
        assert all(0 < i <= 1 for i in muscles.values()), f"{exercise} con intensidad fuera de 0-1"


def test_import_populates_exercise_muscle_from_the_toml(conn, export):
    hevy.import_csv(conn, export, TZ)

    assert conn.execute(
        "SELECT muscle, intensity FROM exercise_muscle WHERE exercise=? ORDER BY intensity DESC",
        ("Sentadilla Hack (Máquina)",),
    ).fetchall() == [("cuadriceps", 1.0), ("gluteo", 0.6), ("femoral", 0.4)]


def test_exercise_muscle_upsert_survives_a_second_import(conn, export):
    hevy.import_csv(conn, export, TZ)
    before = conn.execute("SELECT COUNT(*) FROM exercise_muscle").fetchone()[0]
    hevy.import_csv(conn, export, TZ)
    assert conn.execute("SELECT COUNT(*) FROM exercise_muscle").fetchone()[0] == before


def test_muscle_group_is_the_muscle_with_intensity_one(conn, tmp_path):
    csv_path = write_csv(
        tmp_path / "in.csv",
        [base_row(exercise_title="Press de Banca Inclinado (Mancuerna)")],
    )
    hevy.import_csv(conn, csv_path, TZ)
    assert conn.execute("SELECT muscle_group FROM workout_set").fetchone() == ("pecho",)


def test_unmapped_exercise_is_imported_and_reported(conn, tmp_path):
    csv_path = write_csv(
        tmp_path / "in.csv",
        [base_row(exercise_title="Ejercicio Inventado"), base_row(set_index="1")],
    )
    stats = hevy.import_csv(conn, csv_path, TZ)

    assert stats["unmapped"] == ["Ejercicio Inventado"]
    # La serie no se pierde: entra sin músculo, para que el usuario la vea.
    assert conn.execute(
        "SELECT muscle_group FROM workout_set WHERE exercise='Ejercicio Inventado'"
    ).fetchone() == (None,)


def test_cli_warns_about_unmapped_exercises(conn, tmp_path, capsys, monkeypatch):
    csv_path = write_csv(tmp_path / "in.csv", [base_row(exercise_title="Ejercicio Inventado")])
    monkeypatch.setattr(hevy, "load_config", lambda **_: {"tz": TZ})
    hevy.main(["import", str(csv_path), "--db", str(tmp_path / "cli.db")])

    out = capsys.readouterr().out
    assert "WARN" in out and "Ejercicio Inventado" in out


# ---------------------------------------------------------------------------
# Matching por fecha hevy <-> strap
# ---------------------------------------------------------------------------


def test_exactly_one_strap_session_that_day_gets_linked(conn, export):
    strap_id = add_strap_workout(conn, "2006-07-21", 18)
    stats = hevy.import_csv(conn, export, TZ)

    assert stats["linked"] == 1
    linked = conn.execute(
        "SELECT linked_workout_id FROM workout WHERE source='hevy' AND linked_workout_id IS NOT NULL"
    ).fetchall()
    assert linked == [(strap_id,)]


def test_linking_overwrites_the_hevy_timestamps_with_the_strap_window(conn, export):
    """La hora del CSV es manual; la del reloj es la oficial."""
    strap_id = add_strap_workout(conn, "2006-07-21", 18)
    strap_start, strap_end = conn.execute(
        "SELECT start_ts, end_ts FROM workout WHERE id=?", (strap_id,)
    ).fetchone()

    hevy.import_csv(conn, export, TZ)

    assert conn.execute(
        "SELECT start_ts, end_ts FROM workout WHERE linked_workout_id=?", (strap_id,)
    ).fetchone() == (strap_start, strap_end)


def test_the_link_holds_even_when_the_csv_hour_is_hours_off(conn, tmp_path):
    """El cruce es por FECHA: 3 h de desfase no impiden el vínculo."""
    strap_id = add_strap_workout(conn, "2026-03-03", 20)
    csv_path = write_csv(
        tmp_path / "in.csv",
        [base_row(start_time="3 mar 2026, 08:00", end_time="3 mar 2026, 09:00")],
    )
    stats = hevy.import_csv(conn, csv_path, TZ)

    assert stats["linked"] == 1
    assert conn.execute("SELECT linked_workout_id FROM workout WHERE source='hevy'").fetchone() == (
        strap_id,
    )


def test_no_strap_session_that_day_leaves_the_workout_unlinked_and_warns(conn, export):
    stats = hevy.import_csv(conn, export, TZ)

    assert stats["linked"] == 0
    assert sorted(stats["ambiguous"]) == [(day, 0) for day in FIXTURE_DAYS]
    assert conn.execute(
        "SELECT COUNT(*) FROM workout WHERE source='hevy' AND linked_workout_id IS NOT NULL"
    ).fetchone()[0] == 0


def test_two_strap_sessions_the_same_day_leave_the_workout_unlinked_and_warn(conn, export):
    add_strap_workout(conn, "2006-07-21", 10)
    add_strap_workout(conn, "2006-07-21", 18)
    stats = hevy.import_csv(conn, export, TZ)

    assert stats["linked"] == 0
    assert ("2006-07-21", 2) in stats["ambiguous"]
    assert conn.execute(
        "SELECT COUNT(*) FROM workout WHERE source='hevy' AND linked_workout_id IS NOT NULL"
    ).fetchone()[0] == 0


def test_ambiguous_day_keeps_the_csv_timestamps(conn, tmp_path):
    add_strap_workout(conn, "2026-03-03", 10)
    add_strap_workout(conn, "2026-03-03", 18)
    csv_path = write_csv(tmp_path / "in.csv", [base_row()])
    hevy.import_csv(conn, csv_path, TZ)

    assert conn.execute("SELECT start_ts FROM workout WHERE source='hevy'").fetchone() == (
        hevy.parse_hevy_datetime("3 mar 2026, 10:00", TZ),
    )


def test_only_strength_sessions_of_the_strap_are_candidates(conn, tmp_path):
    """Un 122 (vóley) o un 223 (auto-IA) el mismo día no cuentan."""
    add_strap_workout(conn, "2026-03-03", 9, sport_type=122)
    add_strap_workout(conn, "2026-03-03", 12, sport_type=223)
    strap_id = add_strap_workout(conn, "2026-03-03", 18, sport_type=52)
    csv_path = write_csv(tmp_path / "in.csv", [base_row()])

    stats = hevy.import_csv(conn, csv_path, TZ)

    assert stats["linked"] == 1
    assert conn.execute("SELECT linked_workout_id FROM workout WHERE source='hevy'").fetchone() == (
        strap_id,
    )


def test_a_strap_session_on_another_day_is_not_a_candidate(conn, tmp_path):
    add_strap_workout(conn, "2026-03-04", 10)
    csv_path = write_csv(tmp_path / "in.csv", [base_row()])
    stats = hevy.import_csv(conn, csv_path, TZ)

    assert stats["linked"] == 0
    assert stats["ambiguous"] == [("2026-03-03", 0)]


def test_relinking_clears_a_link_that_no_longer_holds(conn, tmp_path):
    """Si aparece un segundo type-52 ese día, el vínculo previo se retira."""
    add_strap_workout(conn, "2026-03-03", 18)
    csv_path = write_csv(tmp_path / "in.csv", [base_row()])
    assert hevy.import_csv(conn, csv_path, TZ)["linked"] == 1

    add_strap_workout(conn, "2026-03-03", 10)
    stats = hevy.import_csv(conn, csv_path, TZ)

    assert stats["linked"] == 0
    assert conn.execute("SELECT linked_workout_id FROM workout WHERE source='hevy'").fetchone() == (
        None,
    )


def test_linking_is_stable_when_importing_twice(conn, export):
    add_strap_workout(conn, "2006-07-21", 18)
    hevy.import_csv(conn, export, TZ)
    first = conn.execute(
        "SELECT id, linked_workout_id, start_ts, end_ts FROM workout ORDER BY id"
    ).fetchall()

    hevy.import_csv(conn, export, TZ)

    assert conn.execute(
        "SELECT id, linked_workout_id, start_ts, end_ts FROM workout ORDER BY id"
    ).fetchall() == first


# ---------------------------------------------------------------------------
# Migración 004 sobre una DB con datos
# ---------------------------------------------------------------------------


def _db_at_003(tmp_path: Path) -> Path:
    """DB con las migraciones previas a la de Hevy (004) aplicadas."""
    before_004 = tmp_path / "migrations_003"
    before_004.mkdir()
    for name in ("001_initial.sql", "002_raw_ingest_unique.sql", "003_annotation.sql"):
        (before_004 / name).write_text((MIGRATIONS_DIR / name).read_text(), encoding="utf-8")
    db_path = tmp_path / "legacy.db"
    assert db.init_db(db_path, before_004) == ["001", "002", "003"]
    return db_path


def test_migration_004_applies_over_a_db_with_existing_workouts(tmp_path):
    db_path = _db_at_003(tmp_path)
    with sqlite3.connect(db_path) as c:
        c.execute(
            "INSERT INTO workout (source, external_id, sport, sport_type, start_ts, end_ts) "
            "VALUES ('zepp','track-1','fuerza',52,1000,2000)"
        )
        c.execute(
            "INSERT INTO workout_set (workout_id, exercise, set_index, reps, weight_kg) "
            "VALUES (1,'Extensión de Pierna',0,20,70)"
        )

    assert "004" in db.init_db(db_path)

    with sqlite3.connect(db_path) as c:
        assert c.execute("SELECT linked_workout_id FROM workout").fetchall() == [(None,)]
        assert c.execute("SELECT set_type FROM workout_set").fetchall() == [(None,)]
        assert c.execute("SELECT COUNT(*) FROM exercise_muscle").fetchone() == (0,)


def test_migration_004_rejects_an_intensity_out_of_range(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO exercise_muscle VALUES ('X','pecho',1.5)")


def test_exercise_muscle_is_keyed_by_exercise_and_muscle(conn):
    conn.execute("INSERT INTO exercise_muscle VALUES ('X','pecho',1.0)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO exercise_muscle VALUES ('X','pecho',0.5)")
