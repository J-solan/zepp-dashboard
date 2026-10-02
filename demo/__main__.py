"""Levanta la API sobre la BBDD de demostración: sin cuenta de Zepp ni config.

    uv run python -m demo            # http://localhost:8000
    uv run python -m demo --reset    # regenera los datos (deshace lo que hayas tocado)

Usa ``data/demo.db`` y nada más: nunca abre tu ``data/zepp.db`` ni llama a
Zepp (el sync responde 503). Al arrancar, la BBDD se regenera si cambió el día
o si tiene más de 3 horas, para que "hoy" termine cerca de ahora; un servidor
que ya está en marcha no se regenera. ``--reset`` fuerza la regeneración.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn

from backend.api import FRONTEND_DIST, create_app
from demo import seed
from ingest.db import REPO_ROOT

DEMO_DB = REPO_ROOT / "data" / "demo.db"
SYNC_OFF_REASON = "modo demo: sincronización desactivada"
# Hoy debe terminar cerca de ahora; reiniciar dentro de este margen conserva lo tocado.
STALE_AFTER_S = 3 * 3600


def _generated(db_path: Path) -> tuple[str | None, int | None]:
    """(último día, momento de generación) de la demo; (None, None) si no se puede leer."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute("SELECT MAX(day), MAX(last_ok_at) FROM sync_state").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None, None  # a medias o de otra versión: se rehace


def ensure_db(db_path: Path, today: date, *, until: int, reset: bool = False) -> bool:
    """Deja en ``db_path`` una demo que termina ``today``. True si la (re)generó."""
    if not reset and db_path.exists():
        last_day, generated_at = _generated(db_path)
        if last_day == today.isoformat() and generated_at is not None and until - generated_at < STALE_AFTER_S:
            return False
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    seed.build(db_path, today, until=until)
    return True


def make_app(db_path: Path):
    return create_app(db_path=db_path, tz=seed.DEFAULT_TZ, sync_config=None, sync_off_reason=SYNC_OFF_REASON)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="API de zepp-dashboard sobre datos inventados (data/demo.db).")
    parser.add_argument("--reset", action="store_true", help="regenera la BBDD aunque sea de hoy")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    today = datetime.now(ZoneInfo(seed.DEFAULT_TZ)).date()
    if ensure_db(DEMO_DB, today, until=int(time.time()), reset=args.reset):
        print(f"Demo generada en {DEMO_DB}")
    if FRONTEND_DIST.is_dir():
        print(f"Web: http://localhost:{args.port}")
    else:
        print("Web sin compilar: `cd frontend && npm install && npm run dev` -> http://localhost:5173")
    uvicorn.run(make_app(DEMO_DB), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
