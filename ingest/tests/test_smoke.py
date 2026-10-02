"""Smoke test: módulos importables + runner de migraciones.

Verifica que los stubs de ingesta importan, que ``init_db`` crea el esquema
esperado (incl. stress_sample y sync_state) y que el runner es idempotente.
"""

import importlib
import sqlite3

import pytest

from ingest import db

INGEST_MODULES = ["auth", "client", "parsers", "hevy", "run", "db"]

EXPECTED_TABLES = {
    "raw_ingest",
    "biocharge",
    "hr_minute",
    "daily_metrics",
    "sleep_session",
    "sleep_stage",
    "stress_sample",
    "workout",
    "workout_set",
    "sync_state",
    "schema_migrations",
}


@pytest.mark.parametrize("name", INGEST_MODULES)
def test_ingest_modules_importable(name):
    importlib.import_module(f"ingest.{name}")


def _table_names(db_path):
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def _versions_on_disk():
    """Prefijos numéricos de db/migrations/, para no reescribir el test al añadir una."""
    return sorted(p.name.split("_")[0] for p in db.MIGRATIONS_DIR.glob("[0-9]*.sql"))


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "zepp.db"
    applied = db.init_db(db_path)
    assert applied == _versions_on_disk()
    assert EXPECTED_TABLES <= _table_names(db_path)


def test_runner_is_idempotent(tmp_path):
    db_path = tmp_path / "zepp.db"
    db.init_db(db_path)
    applied_second = db.init_db(db_path)
    assert applied_second == []  # nada pendiente en la segunda ejecución
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == len(_versions_on_disk())
