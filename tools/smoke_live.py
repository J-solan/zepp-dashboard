#!/usr/bin/env python3
"""Smoke test MANUAL en vivo de ``ingest.auth`` + ``ingest.client``.

NO corre en CI (usa red real y credenciales reales). Lo ejecuta el usuario a
mano para verificar en vivo que el login de producción y los endpoints
siguen funcionando contra la nube de Zepp.

Pide ``band_data`` de ayer y ``sport_history``, e imprime conteos.

Uso:  uv run python tools/smoke_live.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.auth import ZeppAuth  # noqa: E402
from ingest.config import load_config  # noqa: E402
from ingest.client import ZeppClient  # noqa: E402


def main() -> int:
    config = load_config()

    auth = ZeppAuth(config)
    client = ZeppClient(auth, config)

    print(f"user_id: {client.user_id}")

    yday = (datetime.now(ZoneInfo(config["tz"])) - timedelta(days=1)).date()
    print(f"Día objetivo (ayer, {config['tz']}): {yday.isoformat()}")

    band = client.band_data(yday, yday)
    band_days = band.get("data") or []
    print(f"band_data: {len(band_days)} día(s)")
    for day in band_days:
        has_hr = bool(day.get("data_hr"))
        has_summary = bool(day.get("summary"))
        print(f"  {day.get('date_time')}: data_hr={'sí' if has_hr else 'NO'} summary={'sí' if has_summary else 'NO'}")

    sport = client.sport_history()
    workouts = ((sport.get("data") or {}).get("summary")) or []
    print(f"sport_history: {len(workouts)} workout(s)")
    type_counts: dict[object, int] = {}
    for w in workouts:
        t = w.get("type")
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in sorted(type_counts.items(), key=lambda kv: str(kv[0])):
        print(f"  type={t}: {c}")

    print("\nOK: login + band_data + sport_history funcionan en producción.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
