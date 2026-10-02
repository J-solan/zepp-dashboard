"""Genera ``fixtures/`` (versionadas, anonimizadas) a partir de los payloads
reales de ``fixtures_local/`` (gitignored, nunca commiteados).

Anonimiza identificadores (user_id, ids de dispositivo/cuenta) y REGENERA
sintéticamente las series (bytes de ``data_hr``, ``stage[]`` de sueño,
``samples`` de BioCharge, ``summary[]`` de workouts) manteniendo las mismas
claves/tipos e invariantes (centinelas presentes, duraciones de fase
cuadrando con dp/lt, etc.) sin copiar ningún valor de salud real.

Uso:  uv run python -m ingest.tests.sanitize_fixtures
"""

from __future__ import annotations

import base64
import copy
import csv
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FIXTURES_LOCAL = Path(__file__).parent / "fixtures_local"
FIXTURES_OUT = Path(__file__).parent / "fixtures"

SEED = 42

# Offset fijo aplicado a todos los timestamps reales para no publicar fechas
# reales de la cuenta (~20 años).
OFFSET_SECONDS = 20 * 365 * 86400
OFFSET_DAYS = OFFSET_SECONDS // 86400

FAKE_USER_ID = "1000000001"
FAKE_DEVICE_SOURCE = 1000001  # reemplaza el id de cuenta/dispositivo real
FAKE_DEVICE_SN = "SYNTHDEV0001"
FAKE_UUID = "00000000-0000-4000-8000-000000000000"

_HR_SENTINELS = (0, 254)


def _shift_s(ts: int) -> int:
    return int(ts) - OFFSET_SECONDS


def _shift_ms(ts_ms: int) -> int:
    return int(ts_ms) - OFFSET_SECONDS * 1000


def _epoch_anchor(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


# ---------------------------------------------------------------------------
# band_data_day.json
# ---------------------------------------------------------------------------


def _synthetic_hr_bytes(rng: random.Random) -> bytes:
    values = []
    for minute in range(1440):
        hour = minute // 60
        if hour < 6 or hour >= 23:
            bpm = rng.randint(48, 62)
        elif 6 <= hour < 8:
            bpm = rng.randint(60, 80)
        elif 12 <= hour < 13 or 18 <= hour < 19:
            bpm = rng.randint(100, 145)
        else:
            bpm = rng.randint(65, 95)
        values.append(bpm)
    for idx in rng.sample(range(1440), 8):
        values[idx] = rng.choice(_HR_SENTINELS)
    return bytes(values)


def _synthetic_summary(rng: random.Random, day: date) -> dict:
    anchor = _epoch_anchor(day)  # medianoche UTC del día sanitizado (ancla simple, no tz-aware)

    stage = [
        {"start": 1440, "stop": 1509, "mode": 4},  # ligero, 70 min
        {"start": 1510, "stop": 1569, "mode": 5},  # profundo, 60 min
        {"start": 1570, "stop": 1599, "mode": 8},  # REM, 30 min
        {"start": 1600, "stop": 1659, "mode": 4},  # ligero, 60 min
        {"start": 1660, "stop": 1664, "mode": 7},  # despierto, 5 min
        {"start": 1665, "stop": 1714, "mode": 4},  # ligero, 50 min
    ]
    light_min = 70 + 60 + 50
    deep_min = 60

    slp = {
        "stage": stage,
        "odd_stage": [],
        "spos": 0,
        "spol": 0,
        "spor": 0,
        "spob": 0,
        "st": anchor + 1440 * 60,
        "ed": anchor + 1715 * 60,
        "obt": 10,
        "ebt": 500,
        "dp": deep_min,
        "lt": light_min,
        "wk": 5,
        "wc": 1,
        "supNap": True,
        "supRem": True,
        "is": 30,
        "lb": 10,
        "dt": 30,
        "rhr": rng.randint(45, 60),
        "ss": rng.randint(60, 90),
        "to": 0,
        "sleepSource": FAKE_DEVICE_SOURCE,
        "sleepScoreVersion": "1.0.2",
        "napSleepSource": FAKE_DEVICE_SOURCE,
        "sleepVersion": 0,
        "napVersion": 0,
        "sleepAlgoVersion": "4.0.17",
        "napAlgoVersion": "4.0.17",
    }
    stp = {
        "ttl": rng.randint(3000, 12000),
        "dis": rng.randint(2000, 9000),
        "cal": rng.randint(100, 400),
        "wk": rng.randint(10, 40),
        "rn": rng.randint(0, 100),
        "runDist": rng.randint(0, 3000),
        "runCal": rng.randint(0, 200),
        "stage": [],
        "stepStageSummary": [],
    }
    return {
        "v": "6",
        "goal": 8000,
        "tz": "3600",
        "algv": "2.13.14",
        "sn": FAKE_DEVICE_SN,
        "byteLength": 8,
        "sync": anchor + 86000,
        "slp": slp,
        "stp": stp,
    }


def sanitize_band_data(real: dict, rng: random.Random) -> dict:
    item = real["data"][0]
    day_fake = date.fromisoformat(item["date_time"]) - timedelta(days=OFFSET_DAYS)

    hr_bytes = _synthetic_hr_bytes(rng)
    summary_obj = _synthetic_summary(rng, day_fake)
    fake_raw_len = len(base64.b64decode(item["data"]))

    fake_item = {
        "uid": FAKE_USER_ID,
        "data_type": item["data_type"],
        "date_time": day_fake.isoformat(),
        "source": FAKE_DEVICE_SOURCE,
        "summary": base64.b64encode(json.dumps(summary_obj).encode()).decode(),
        "device_id": FAKE_DEVICE_SN,
        "uuid": FAKE_UUID,
        "data": base64.b64encode(bytes(rng.randrange(256) for _ in range(fake_raw_len))).decode(),
        "data_hr": base64.b64encode(hr_bytes).decode(),
    }
    return {"code": real["code"], "message": real["message"], "data": [fake_item]}


# ---------------------------------------------------------------------------
# biocharge_day.json
# ---------------------------------------------------------------------------


def _synthetic_biocharge_samples(rng: random.Random) -> list[dict]:
    samples = []
    level = rng.uniform(55, 70)
    for minute in range(1440):
        level += rng.uniform(-1.5, 1.5)
        level = max(0.0, min(100.0, level))
        mental = max(0.0, min(100.0, level + rng.uniform(-10, 10)))
        physical = max(0.0, min(100.0, level + rng.uniform(-10, 10)))
        samples.append(
            {
                "s": minute * 60000,
                "total": int(round(level)),
                "mental": round(mental, 4),
                "physical": round(physical, 4),
                "status": 0,
                "jsonExtra": "{}",
            }
        )
    return samples


def sanitize_biocharge(real: dict, rng: random.Random) -> dict:
    item = real["items"][0]
    value = item["value"]
    fake_item = {
        "userId": FAKE_USER_ID,
        "eventType": item["eventType"],
        "subType": item["subType"],
        "timestamp": _shift_ms(item["timestamp"]),
        "value": {
            "startTime": _shift_ms(value["startTime"]),
            "deviceId": value["deviceId"],
            "deviceSN": value["deviceSN"],
            "deviceSource": value["deviceSource"],
            "deviceType": value["deviceType"],
            "timeZone": value["timeZone"],
            "samples": _synthetic_biocharge_samples(rng),
        },
    }
    return {"items": [fake_item]}


# ---------------------------------------------------------------------------
# sport_history.json
# ---------------------------------------------------------------------------

# Campos con datos de salud/actividad reales que varían por workout: se
# regeneran siempre. El resto de ~150 campos del template son constantes de
# protocolo (sentinelas -1/-20000/... o valores por defecto), iguales para
# cualquier cuenta, y se copian tal cual del primer workout real.

_SYNTHETIC_WORKOUTS = [
    # (type, con_centinelas)
    (52, True),
    (52, False),
    (52, False),
    (223, False),
    (223, False),
    (223, False),
    (122, False),
    (777, False),  # code fuera del mapa sport_types -> 'pending'
]


def _sport_template(real_summary: list[dict]) -> dict:
    template = copy.deepcopy(real_summary[0])
    template["source"] = "run.SYNTHDEV0001.huami.com"
    template["bind_device"] = "0:SYNTH_STRAP:SYNTHDEV0001:0.0.0.0"
    template["deviceid"] = FAKE_DEVICE_SN
    template["sn"] = FAKE_DEVICE_SN
    template["devicesource"] = FAKE_DEVICE_SN
    return template


def _synthetic_workout(template: dict, rng: random.Random, anchor: int, index: int, sport_type: int, sentinel: bool) -> dict:
    w = copy.deepcopy(template)
    start = anchor + index * 2 * 86400 + rng.randint(0, 3600)
    duration = rng.randint(600, 4200)

    w["trackid"] = str(start)
    w["end_time"] = str(start + duration)
    w["run_time"] = str(duration)
    w["createTime"] = (start + duration) * 1000 + rng.randint(0, 999)
    w["updateTime"] = w["createTime"]
    w["type"] = sport_type
    w["auto_recognition"] = sport_type == 223

    if sentinel:
        w["avg_heart_rate"] = "-1.0"
        w["max_heart_rate"] = -1
        w["min_heart_rate"] = -1
        w["calorie"] = "-1.0"
        w["exercise_load"] = -1
        w["te"] = -1
        w["heart_range"] = ""
    else:
        max_hr = rng.randint(120, 175)
        min_hr = rng.randint(60, max_hr - 20)
        w["avg_heart_rate"] = f"{rng.randint(min_hr + 5, max_hr - 5)}.0"
        w["max_heart_rate"] = max_hr
        w["min_heart_rate"] = min_hr
        w["calorie"] = f"{rng.randint(50, 600)}.0"
        w["exercise_load"] = rng.randint(0, 40)
        w["te"] = rng.randint(0, 50)
        w["heart_range"] = (
            f"{rng.randint(0,300)},{min_hr};{rng.randint(200,2000)},{(min_hr+max_hr)//2};"
            f"{rng.randint(0,500)},{max_hr}"
        )

    w["avg_frequency"] = f"{rng.randint(30, 60)}.0"
    w["max_frequency"] = rng.randint(60, 170)
    w["anaerobic_te"] = 0 if sentinel else rng.randint(0, 30)

    if sport_type == 52 and not sentinel:
        n_sets = rng.randint(3, 6)
        w["total_group"] = n_sets
        w["strengthScores"] = json.dumps([round(rng.uniform(60, 95), 1) for _ in range(n_sets)])
        w["strength_training_group"] = json.dumps(
            [{"actionType": rng.choice([0, 0, 61, 12]), "count": rng.randint(5, 20)} for _ in range(n_sets)]
        )
    else:
        w["total_group"] = 0
        w["strengthScores"] = ""
        w["strength_training_group"] = ""

    return w


def sanitize_sport_history(real: dict, rng: random.Random) -> dict:
    real_summary = real["data"]["summary"]
    template = _sport_template(real_summary)
    anchor = _shift_s(min(int(w["trackid"]) for w in real_summary))

    workouts = [
        _synthetic_workout(template, rng, anchor, i, sport_type, sentinel)
        for i, (sport_type, sentinel) in enumerate(_SYNTHETIC_WORKOUTS)
    ]
    return {
        "code": real["code"],
        "message": real["message"],
        "data": {"next": real["data"].get("next", -1), "summary": workouts},
    }


# ---------------------------------------------------------------------------
# hevy_export.csv
# ---------------------------------------------------------------------------

# El export de Hevy no lleva identificadores de cuenta: lo sensible son los
# PESOS, las REPS y las FECHAS (revelan el nivel y la rutina reales). Los
# ``exercise_title`` SÍ se conservan tal cual — son el catálogo público de Hevy
# y la clave con la que ``muscle_map.toml`` mapea los músculos, así que
# cambiarlos volvería inútil la fixture.

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]


def _shift_hevy_datetime(text: str, minute_jitter: int) -> str:
    """``'16 jul 2026, 14:24'`` → misma forma, ~20 años atrás y con la hora
    movida unos minutos (son horas tecleadas a mano, no medidas)."""
    date_part, _, time_part = text.partition(",")
    day, month, year = date_part.split()
    hour, minute = time_part.strip().split(":")
    month_index = [m[:3] for m in _MESES].index(month.lower().rstrip(".")[:3])

    shifted = datetime(int(year), month_index + 1, int(day), int(hour), int(minute)) + timedelta(
        days=-OFFSET_DAYS, minutes=minute_jitter
    )
    return f"{shifted.day} {_MESES[shifted.month - 1]} {shifted.year}, {shifted:%H:%M}"


def sanitize_hevy_export(rows: list[dict], rng: random.Random) -> list[dict]:
    # Un jitter por workout (no por fila): las 3 columnas de tiempo de un mismo
    # entreno tienen que seguir cuadrando entre sí.
    jitter: dict[str, int] = {}

    out = []
    for row in rows:
        fake = dict(row)
        start = row["start_time"]
        jitter.setdefault(start, rng.randint(-90, 90))
        fake["start_time"] = _shift_hevy_datetime(start, jitter[start])
        fake["end_time"] = _shift_hevy_datetime(row["end_time"], jitter[start])

        # Perturbación SIEMPRE distinta de cero: un jitter que puede salir 0
        # dejaría publicadas marcas reales del usuario tal cual.
        if row["weight_kg"]:
            # Escalado del 15-40% + redondeo a 0.5 kg: mantiene el orden de
            # magnitud (una prensa pesa más que un curl) sin la marca real.
            factor = 1 + rng.choice([-1, 1]) * rng.uniform(0.15, 0.40)
            fake["weight_kg"] = f"{round(float(row['weight_kg']) * factor * 2) / 2:g}"
        if row["reps"]:
            fake["reps"] = str(max(1, int(row["reps"]) + rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])))
        out.append(fake)
    return out


# ---------------------------------------------------------------------------


def main() -> None:
    if not FIXTURES_LOCAL.exists():
        raise SystemExit(f"No existe {FIXTURES_LOCAL}")

    FIXTURES_OUT.mkdir(parents=True, exist_ok=True)

    band_real = json.loads((FIXTURES_LOCAL / "band_data_day.json").read_text())
    charge_real = json.loads((FIXTURES_LOCAL / "biocharge_day.json").read_text())
    sport_real = json.loads((FIXTURES_LOCAL / "sport_history.json").read_text())

    band_fake = sanitize_band_data(band_real, random.Random(SEED))
    charge_fake = sanitize_biocharge(charge_real, random.Random(SEED + 1))
    sport_fake = sanitize_sport_history(sport_real, random.Random(SEED + 2))

    (FIXTURES_OUT / "band_data_day.json").write_text(json.dumps(band_fake, indent=2) + "\n")
    (FIXTURES_OUT / "biocharge_day.json").write_text(json.dumps(charge_fake, indent=2) + "\n")
    (FIXTURES_OUT / "sport_history.json").write_text(json.dumps(sport_fake, indent=2) + "\n")

    hevy_path = FIXTURES_LOCAL / "hevy_export.csv"
    with open(hevy_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        hevy_fake = sanitize_hevy_export(list(reader), random.Random(SEED + 3))
    with open(FIXTURES_OUT / "hevy_export.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(hevy_fake)

    print(f"Fixtures sanitizadas escritas en {FIXTURES_OUT}")


if __name__ == "__main__":
    main()
