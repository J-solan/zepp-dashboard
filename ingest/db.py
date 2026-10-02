"""Runner de migraciones mínimo para la base SQLite de zepp-dashboard.

Aplica en orden los ficheros ``NNN_*.sql`` pendientes de ``db/migrations/``,
registrando las versiones ya aplicadas en la tabla ``schema_migrations``.
Idempotente: correr N veces = correr 1 vez. Activa WAL.

Uso:  uv run python -m ingest.db
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "zepp.db"

# Fichero de migración = prefijo numérico + '_' + descripción + '.sql'
_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def _pending(conn: sqlite3.Connection, migrations_dir: Path) -> list[tuple[str, Path]]:
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    pending: list[tuple[str, Path]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _MIGRATION_RE.match(path.name)
        if not match:
            continue
        version = match.group(1)
        if version not in applied:
            pending.append((version, path))
    return pending


def init_db(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path | str = MIGRATIONS_DIR,
) -> list[str]:
    """Aplica las migraciones pendientes y devuelve las versiones aplicadas."""
    db_path = Path(db_path)
    migrations_dir = Path(migrations_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
        )
        conn.commit()

        applied: list[str] = []
        for version, path in _pending(conn, migrations_dir):
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, int(time.time())),
            )
            conn.commit()
            applied.append(version)
        return applied
    finally:
        conn.close()


def main() -> None:
    applied = init_db()
    if applied:
        print(f"Migraciones aplicadas: {', '.join(applied)}")
    else:
        print("Sin migraciones pendientes.")


if __name__ == "__main__":
    main()
