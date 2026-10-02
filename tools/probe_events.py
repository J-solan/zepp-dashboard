#!/usr/bin/env python3
"""Sonda MANUAL de ``/v2/users/me/events``. NO corre en CI (usa red real).

**Para qué**: el endpoint de eventos es multiuso y lo que devuelve depende del
par ``eventType``/``subType`` que le pases. No hay documentación ni endpoint
que los liste, y **tu dispositivo puede exponer pares distintos** a los de la
tabla de ``docs/zepp-api.md``. Esta sonda prueba los candidatos conocidos
contra TU cuenta y te dice cuáles devuelven datos.

Toda respuesta NO vacía se guarda cruda en ``raw_ingest`` con
``source='probe:<preset>'`` y se imprime la combinación ganadora más un sample
de su estructura. **NO parsea nada**: es material para diseccionar a mano.

Uso:  uv run python tools/probe_events.py [--days N]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.auth import ZeppAuth  # noqa: E402
from ingest.config import load_config  # noqa: E402
from ingest.client import ZeppAPIError, ZeppClient  # noqa: E402
from ingest.db import DEFAULT_DB_PATH, init_db  # noqa: E402
from ingest.run import store_raw  # noqa: E402

# preset -> pares (eventType, subType) a probar EN ORDEN; se para en el primero
# que devuelva datos.
#
# Adivinar el literal a ojo casi nunca funciona: tantear variantes de
# capitalización solo acertó respiratory y daily_health. Los pares exactos salen
# de `_EVENT_PRESETS` del proyecto `zepp-health-cli`. Los que no se adivinan:
#   readiness  -> el eventType es correcto, pero el subType es 'watch_score'
#   stress     -> no tiene eventType propio: viaja como Charge/'stress_data'
#   hrv        -> el literal es 'hrv_sdnn', no 'hrv'
#   hrv-rmssd  -> el literal es 'HRVRMSSD' (sin guion ni guion bajo)
#
# Si sospechas que tu reloj expone algo que no está aquí, añade el par y prueba.
PRESETS: dict[str, list[tuple[str, str]]] = {
    # --- pendientes de validar (candidatos de zepp-health-cli) ---
    "readiness": [("readiness", "watch_score"), ("readiness", "real_data")],
    "hrv_sdnn": [("hrv_sdnn", "real_data"), ("HRVSDNN", "real_data")],
    "hrv_rmssd": [("HRVRMSSD", "real_data"), ("hrv_rmssd", "real_data")],
    "stress": [("Charge", "stress_data"), ("stress", "real_data")],
    "emotion": [("Emotion", "real_data")],
    "blood_pressure": [("blood_pressure", "real_data")],
    "lactate_threshold": [("LactateThreshold", "summary")],
    "temperature": [("readiness", "watch_score")],
    # --- ya confirmados: se re-sondean como control ---
    "respiratory": [("RespiratoryRate", "real_data")],
    "daily_health": [("DailyHealth", "summary")],
    "charge_control": [("Charge", "real_data")],
}

# Presets del scope de usuario ``/users/{id}/events`` (subType=None), que es un
# scope DISTINTO del de arriba. Aquí vive la serie de estrés que pinta la app:
# el blob de ``Charge/stress_data`` no la contiene (ver docs/zepp-api.md).
USER_EVENT_PRESETS: dict[str, str] = {
    "all_day_stress": "all_day_stress",
    "single_stress": "single_stress",
}


def _items(payload) -> list:
    """Los eventos vienen en ``items``; se aceptan otras formas por si acaso."""
    if isinstance(payload, dict):
        for key in ("items", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return payload if isinstance(payload, list) else []


def _describe(items: list) -> str:
    first = items[0]
    if not isinstance(first, dict):
        return f"    sample: {json.dumps(first, ensure_ascii=False)[:200]}"
    lines = [f"    claves item: {sorted(first)}"]
    value = first.get("value")
    if isinstance(value, dict):
        lines.append(f"    claves value: {sorted(value)}")
        for key, sub in value.items():
            if isinstance(sub, list) and sub:
                lines.append(f"    value[{key!r}][0]: {json.dumps(sub[0], ensure_ascii=False)[:200]}")
                break
    lines.append(f"    item[0] crudo: {json.dumps(first, ensure_ascii=False)[:400]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="probe_events.py", description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="ventana hacia atrás (default: 7)")
    args = parser.parse_args()

    config = load_config()

    tz = ZoneInfo(config["tz"])
    now = datetime.now(tz)
    to_ms = int(now.timestamp() * 1000)
    from_ms = int((now - timedelta(days=args.days)).timestamp() * 1000)
    day_key = now.date().isoformat()
    print(f"Ventana: últimos {args.days} día(s) → [{from_ms}, {to_ms}]\n")

    init_db()
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    client = ZeppClient(ZeppAuth(config), config)

    hits: list[tuple[str, str, str, int]] = []
    try:
        for preset, candidates in PRESETS.items():
            print(f"[{preset}]")
            for event_type, sub_type in candidates:
                try:
                    payload = client.events(event_type, sub_type, from_ms, to_ms)
                except ZeppAPIError as exc:
                    print(f"  {event_type}/{sub_type}: ERROR {exc}")
                    continue
                items = _items(payload)
                if not items:
                    print(f"  {event_type}/{sub_type}: vacío")
                    continue

                hits.append((preset, event_type, sub_type, len(items)))
                store_raw(conn, f"probe:{preset}", f"{day_key}:{event_type}:{sub_type}", payload)
                print(f"  {event_type}/{sub_type}: {len(items)} item(s)  <-- DATOS")
                print(_describe(items))
                break  # candidato encontrado: no hace falta seguir probando

        for preset, event_type in USER_EVENT_PRESETS.items():
            print(f"[{preset}] (/users/{{id}}/events)")
            try:
                payload = client.events_user(event_type, from_ms, to_ms)
            except ZeppAPIError as exc:
                print(f"  {event_type}: ERROR {exc}")
                continue
            items = _items(payload)
            if not items:
                print(f"  {event_type}: vacío")
                continue
            hits.append((preset, event_type, "-", len(items)))
            store_raw(conn, f"probe:{preset}", f"{day_key}:{event_type}", payload)
            print(f"  {event_type}: {len(items)} item(s)  <-- DATOS")
            print(_describe(items))
    finally:
        conn.close()

    print("\n--- Resumen ---")
    if not hits:
        print("Ninguna combinación devolvió datos.")
    for preset, event_type, sub_type, count in hits:
        print(f"  {preset}: eventType={event_type} subType={sub_type} -> {count} item(s)")
    print(f"\nCrudos guardados en raw_ingest (source='probe:<preset>') de {DEFAULT_DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
