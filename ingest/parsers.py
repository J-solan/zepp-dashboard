"""Parsers de payloads: ``data_hr`` (bytes + centinelas) y ``slp`` (fases).

Decodifica la FC continua (1 byte = 1 muestra/min, descartando centinelas 0 y
254) y las fases de sueño desde el blob base64. Ver docs/zepp-api.md, "Payload traps".

Funciones puras: dict -> estructuras Python. Sin red ni DB.
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_HR_SENTINELS = {0, 254}
_HR_MIN, _HR_MAX = 30, 220

# Respiratorio: único centinela observado = 0 (ver parse_respiratory). El rango
# es una red de seguridad por si aparece otro centinela: 4-60 rpm cubre de
# sobra lo humano (observado en esta cuenta: 14-21).
_RESP_SENTINEL = 0
_RESP_MIN, _RESP_MAX = 4, 60

_SPORT_SENTINELS = {-1, -20000, -274, -361}

# Hueco (minutos) a partir del cual dos tramos de ``odd_stage`` son siestas
# distintas. En el crudo real los tramos de una misma siesta van PEGADOS y
# entre siestas hay 85+ minutos, así que cualquier umbral entre 1 y 80 da el
# mismo resultado; 5 deja margen por si algún día aparece un microhueco.
_NAP_GAP_MIN = 5

_READINESS_SENTINEL = 255
_READINESS_CORE_KEYS = {"rdnsScore", "sleepHRV", "sleepRHR"}
# Bookkeeping/metadato de la propia entrada: no son "scores" -> fuera del dict extra.
_READINESS_META_KEYS = {
    "timestamp",
    "timestampUpdate",
    "timezoneId",
    "status",
    "algVer",
    "algSubVer",
    "deviceId",
    "deviceSource",
    "insightId",
}

_STRESS_MINUTES_PER_DAY = 1440
_STRESS_MIN, _STRESS_MAX = 0, 100

# BioCharge: centinela "sin calcular" SOLO en 'total' (validado con datos
# reales: tandas contiguas de pocos minutos, en mitad del día -no solo al
# final-, con 'mental'/'physical' ininterrumpidos y coherentes con las
# muestras vecinas, y 'status' siempre 0 -> no correla, no sirve de filtro).
_BIOCHARGE_TOTAL_SENTINEL = 255


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=tz)


def parse_hr_minute(band_day: dict, tz: str) -> list[tuple[int, int]]:
    """``data_hr`` base64 -> lista de (ts_utc, bpm), 1 byte = 1 min.

    Índice 0 = medianoche local (``date_time``) del propio día. Descarta
    centinelas (0, 254) y cualquier valor fuera de 30-220.
    """
    zone = ZoneInfo(tz)
    day = date.fromisoformat(band_day["date_time"])
    midnight = _local_midnight(day, zone)
    raw = base64.b64decode(band_day["data_hr"])

    result: list[tuple[int, int]] = []
    for minute, bpm in enumerate(raw):
        if bpm in _HR_SENTINELS or not (_HR_MIN <= bpm <= _HR_MAX):
            continue
        ts = int((midnight + timedelta(minutes=minute)).timestamp())
        result.append((ts, bpm))
    return result


def parse_sleep(band_day: dict, tz: str) -> tuple[dict, list[dict]]:
    """``summary`` base64 -> JSON, campo ``slp`` -> (session, stages).

    ``stage[]`` viene en minutos-desde-medianoche local con `stop` inclusivo
    (duración = stop - start + 1), referidos a la medianoche del día ANTERIOR
    a ``date_time`` (verificado empíricamente contra `st`/`ed`, que son unix s
    directos). ``dp``/``lt`` se toman tal cual; `rem_min`/`awake_min` se
    derivan sumando duraciones de mode 8/7 respectivamente.
    """
    zone = ZoneInfo(tz)
    day = date.fromisoformat(band_day["date_time"])
    reference = _local_midnight(day - timedelta(days=1), zone)

    summary = json.loads(base64.b64decode(band_day["summary"]))
    slp = summary["slp"]

    stages: list[dict] = []
    rem_min = 0
    awake_min = 0
    for entry in slp["stage"]:
        start, stop, mode = entry["start"], entry["stop"], entry["mode"]
        duration = stop - start + 1
        start_ts = int((reference + timedelta(minutes=start)).timestamp())
        end_ts = int((reference + timedelta(minutes=stop + 1)).timestamp())
        stages.append({"start_ts": start_ts, "end_ts": end_ts, "stage": mode})
        if mode == 8:
            rem_min += duration
        elif mode == 7:
            awake_min += duration

    session = {
        "start_ts": slp["st"],
        "end_ts": slp["ed"],
        "score": slp["ss"],
        "deep_min": slp["dp"],
        "light_min": slp["lt"],
        "rem_min": rem_min,
        "awake_min": awake_min,
        "wake_count": slp["wc"],
        "resting_hr": slp["rhr"],
        "tz": tz,
        "is_nap": 0,
    }
    return session, stages


def parse_naps(band_day: dict, tz: str) -> list[tuple[dict, list[dict]]]:
    """``slp.odd_stage`` -> [(session, stages)], una por siesta.

    Mismo formato y mismo anclaje que ``stage[]`` (minutos desde la medianoche
    del día ANTERIOR, ``stop`` inclusivo), pero es una lista de tramos SUELTOS
    repartidos por el día, no una sesión continua. Verificado sobre 22 días de
    crudo real: los tramos de una misma siesta van pegados
    (``start == anterior.stop + 1``) y entre siestas distintas hay huecos de
    85 minutos o más.

    Por eso se agrupa por contigüidad y NO por tramo: una siesta puede llevar
    dentro un tramo ``mode=7`` (despierto) de varios minutos —visto uno de 11—
    y trocearla ahí daría tres siestas donde hubo una.

    Una siesta no trae ``ss``/``rhr``/``wc``: esos son del sueño nocturno y
    quedan a ``None``. ``deep_min``/``light_min`` se derivan sumando, porque
    tampoco hay ``dp``/``lt`` para ellas.
    """
    summary = json.loads(base64.b64decode(band_day["summary"]))
    segments = (summary.get("slp") or {}).get("odd_stage")
    if not segments:
        return []

    zone = ZoneInfo(tz)
    day = date.fromisoformat(band_day["date_time"])
    reference = _local_midnight(day - timedelta(days=1), zone)

    groups: list[list[dict]] = []
    for entry in sorted(segments, key=lambda e: e["start"]):
        if groups and entry["start"] - groups[-1][-1]["stop"] <= _NAP_GAP_MIN:
            groups[-1].append(entry)
        else:
            groups.append([entry])

    naps: list[tuple[dict, list[dict]]] = []
    for group in groups:
        stages: list[dict] = []
        minutes = {4: 0, 5: 0, 7: 0, 8: 0}
        for entry in group:
            start, stop, mode = entry["start"], entry["stop"], entry["mode"]
            if mode in minutes:
                minutes[mode] += stop - start + 1
            stages.append(
                {
                    "start_ts": int((reference + timedelta(minutes=start)).timestamp()),
                    "end_ts": int((reference + timedelta(minutes=stop + 1)).timestamp()),
                    "stage": mode,
                }
            )
        naps.append(
            (
                {
                    "start_ts": stages[0]["start_ts"],
                    "end_ts": stages[-1]["end_ts"],
                    "score": None,
                    "deep_min": minutes[5],
                    "light_min": minutes[4],
                    "rem_min": minutes[8],
                    "awake_min": minutes[7],
                    "wake_count": None,
                    "resting_hr": None,
                    "tz": tz,
                    "is_nap": 1,
                },
                stages,
            )
        )
    return naps


def parse_daily_from_band(band_day: dict) -> dict | None:
    """Pasos/cal del bloque ``stp`` del ``summary``, si existe."""
    summary = json.loads(base64.b64decode(band_day["summary"]))
    stp = summary.get("stp")
    if not stp:
        return None
    return {"steps": stp["ttl"], "calories": stp["cal"]}


def parse_biocharge(events_payload: dict) -> list[tuple[int, int | None, float, float, int]]:
    """``value.samples[]`` -> (ts_utc, total, mental, physical, status).

    ``s`` = offset en ms desde ``value.startTime`` (ambos unix ms UTC).

    ``total`` trae centinela **255** en tandas cortas donde el fusion score
    aún no está calculado (visto en pleno día, no solo al final de la
    ventana sincronizada) -> se guarda como ``None``. ``mental``/``physical``
    NO comparten ese hueco (siguen su tendencia normal sample a sample) así
    que se conservan tal cual: la muestra no se descarta entera.
    """
    result: list[tuple[int, int | None, float, float, int]] = []
    for item in events_payload.get("items") or []:
        value = item.get("value") or {}
        start_time = value["startTime"]
        for sample in value.get("samples") or []:
            ts = (start_time + sample["s"]) // 1000
            total = sample["total"]
            if total == _BIOCHARGE_TOTAL_SENTINEL:
                total = None
            result.append((ts, total, sample["mental"], sample["physical"], sample["status"]))
    return result


def parse_respiratory(events_payload: dict) -> list[tuple[int, int]]:
    """``RespiratoryRate/real_data`` -> lista de (ts_utc, rpm), 1 byte = 1 min.

    Diseccionado sobre 6 días de crudo real (``raw_ingest``,
    ``source='probe:respiratory'``):

    - ``value.measurements`` = **string base64 de 1440 bytes** = 1 byte por
      minuto de día completo (misma cadencia que ``data_hr``).
    - **Centinela = 0** (950-1339 bytes por día: solo se mide dormido y a
      ratos). NO aparecen 254/255. Valores reales observados: 14-21 rpm.
    - **Anclaje: ``ts = item.timestamp/1000 + minuto*60``**, es decir índice 0
      = **medianoche UTC** de ese día. Sin corrección de offset. Validado
      empíricamente por dos vías independientes:
        1. El bloque nocturno de medición termina a -18/+7/+5 min del despertar
           real (``slp.ed`` de band_data) en los 3 días con solape. Restando el
           offset del payload daría -78/-53/-55 min (~1 h antes, sistemático).
        2. En un día parcial, la serie de biocharge (mismo endpoint, misma
           convención ``startTime + s``) termina a 1 min de la última muestra
           válida de ``data_hr``, cuyo anclaje está validado.
    - ``value.timeZone`` = ``[{period: [min_ini, min_fin], offset: segundos}]``
      es **METADATO, no anclaje**: segmenta el tramo medido del día indicando
      qué offset UTC regía en el dispositivo en cada rango (los ``period``
      acotan exactamente los bytes no-cero, verificado 6/6 días). Sirve para
      renderizar en hora local del dispositivo y para la "tz efectiva por día"
      por día. Ojo: reporta ``3600`` en pleno verano de Madrid
      (donde correspondería 7200), otra razón para no usarlo como offset.
    """
    result: list[tuple[int, int]] = []
    for item in events_payload.get("items") or []:
        value = item.get("value") or {}
        measurements = value.get("measurements")
        if not measurements:
            continue
        start_ts = item["timestamp"] // 1000
        for minute, rpm in enumerate(base64.b64decode(measurements)):
            if rpm == _RESP_SENTINEL or not (_RESP_MIN <= rpm <= _RESP_MAX):
                continue
            result.append((start_ts + minute * 60, rpm))
    return result


def parse_daily_health(events_payload: dict) -> list[dict]:
    """``DailyHealth/summary`` -> [{'day', 'steps', 'calories'}].

    Un item por día, con un único ``value.samples[0]``. El día se toma de
    ``dateString`` (el día local ya resuelto por el servidor), no del
    ``timestamp``. ``value.timeZone`` aquí es la cadena inútil
    ``"1,Asia/Shanghai"`` (default de servidor, ver docs/zepp-api.md), no la estructura de
    periodos de ``RespiratoryRate``.

    Contrastado contra el bloque ``stp`` de band_data en los 3 días con solape:
    ``totalSteps``/``totalCalories`` coinciden exactamente con ``ttl``/``cal``.
    """
    result: list[dict] = []
    for item in events_payload.get("items") or []:
        for sample in (item.get("value") or {}).get("samples") or []:
            day = sample.get("dateString")
            if not day:
                continue
            result.append(
                {
                    "day": day,
                    "steps": sample.get("totalSteps"),
                    "calories": sample.get("totalCalories"),
                }
            )
    return result


def _watch_statistics_series(payload: dict, value_keys: tuple[str, ...]) -> list[tuple[str, float]]:
    """``WatchSportStatistics`` -> [(day, valor)] con el primer key presente.

    Forma de la respuesta (según ``zepp-health-cli``): ``items[]`` con
    ``dayId`` + las métricas. ``dayId`` puede venir como ``'YYYY-MM-DD'`` o
    como entero ``YYYYMMDD``; se normaliza a ISO.

    ``value_keys`` son nombres ALTERNATIVOS del mismo dato (versiones de API),
    no un fallback de valor: manda el primero que EXISTA en la fila. Si ese
    campo está pero vale None/-1, el día no tiene dato y se omite — encadenar
    al siguiente key mezclaría métricas distintas.
    """
    series: list[tuple[str, float]] = []
    for row in payload.get("items") or []:
        day_id = row.get("dayId")
        if day_id is None:
            continue
        day = str(day_id)
        if len(day) == 8 and day.isdigit():
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        for key in value_keys:
            if key not in row:
                continue
            value = row[key]
            if value is not None and value != -1:
                series.append((day, value))
            break
    return series


def parse_sport_load(payload: dict) -> list[tuple[str, float]]:
    """SPORT_LOAD -> [(day, train_load)].

    ``currnetDayTrainLoad`` (typo de la API, sic) es la carga DEL DÍA, que es
    lo que guarda ``daily_metrics.train_load``. ``wtlSum`` (acumulado semanal)
    solo se usa si la fila NO trae el campo diario: son métricas distintas y no
    deben mezclarse. Estructura tomada de ``zepp-health-cli`` (no hay crudo
    real todavía: validación en vivo pendiente del usuario).
    """
    return _watch_statistics_series(payload, ("currnetDayTrainLoad", "wtlSum"))


def parse_vo2max(payload: dict) -> list[tuple[str, float]]:
    """VO2_MAX -> [(day, vo2max)].

    Mismo contenedor que SPORT_LOAD. El nombre exacto del campo de valor NO
    está confirmado (``zepp-health-cli`` expone el endpoint pero no consume la
    respuesta, y esta cuenta aún no ha devuelto crudo): se prueban los
    candidatos en orden. Pendiente de validación en vivo.
    """
    return _watch_statistics_series(payload, ("vo2max", "vo2Max", "value"))


def _sport_sentinel_to_none(value):
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    if numeric in _SPORT_SENTINELS:
        return None
    return value


def parse_sport_history(payload: dict, sport_types: dict) -> list[dict]:
    """``data.summary[]`` -> lista de workout_dict (campos en docs/zepp-api.md, "Workouts").

    Centinelas -1/-20000/-274/-361 -> None. ``te`` viene *10 en el payload
    real (rango observado 0-50) -> se escala a 1.0-5.0 dividiendo entre 10.
    ``review_status``: 'pending' si type==223 o el code no está en
    ``sport_types``; resto -> 'auto'.
    """
    known_codes = {str(code) for code in sport_types}
    workouts: list[dict] = []
    for w in (payload.get("data") or {}).get("summary") or []:
        sport_type = w["type"]
        te_raw = _sport_sentinel_to_none(w.get("te"))
        avg_hr = _sport_sentinel_to_none(w.get("avg_heart_rate"))
        max_hr = _sport_sentinel_to_none(w.get("max_heart_rate"))
        min_hr = _sport_sentinel_to_none(w.get("min_heart_rate"))
        calorie = _sport_sentinel_to_none(w.get("calorie"))
        exercise_load = _sport_sentinel_to_none(w.get("exercise_load"))

        review_status = (
            "pending"
            if sport_type == 223 or str(sport_type) not in known_codes
            else "auto"
        )

        workouts.append(
            {
                "trackid": int(w["trackid"]),
                "source": w.get("source"),
                "end_time": int(w["end_time"]),
                "run_time": int(w["run_time"]),
                "type": sport_type,
                "avg_heart_rate": float(avg_hr) if avg_hr is not None else None,
                "max_heart_rate": int(max_hr) if max_hr is not None else None,
                "min_heart_rate": int(min_hr) if min_hr is not None else None,
                "calorie": float(calorie) if calorie is not None else None,
                "exercise_load": int(exercise_load) if exercise_load is not None else None,
                "te": (float(te_raw) / 10.0) if te_raw is not None else None,
                "heart_range": w.get("heart_range"),
                # Nombre que el usuario le puso en la app ("Bici trabajo").
                # Viene vacío la mayoría de las veces y NO es una etiqueta de
                # deporte, pero cuando está identifica la sesión al instante:
                # pre-rellena el título en lugar de preguntar por él.
                "sport_title": (w.get("sport_title") or "").strip() or None,
                "strengthScores": w.get("strengthScores"),
                "auto_recognition": w.get("auto_recognition"),
                "syncedTimezone": w.get("syncedTimezone"),
                "review_status": review_status,
            }
        )
    return workouts


def _readiness_sentinel_to_none(value):
    return None if value == _READINESS_SENTINEL else value


def parse_readiness(events_payload: dict, tz: str) -> list[dict]:
    """``readiness/watch_score`` -> [{day, readiness, sleepHRV, sleepRHR, extra}].

    Diseccionado sobre 9 eventos reales (``raw_ingest``,
    ``source='probe:readiness'``): el DÍA se toma de ``value.timestamp``, que
    en los 9/9 eventos cae EXACTO en medianoche local (00:00:00 de la tz
    configurada) del día que puntúa. ``item.timestamp`` (== ``value.
    timestampUpdate``) es la hora en que Zepp CALCULÓ ese score (típicamente
    al despertar), no el día en sí: puede caer horas después e incluso, en
    cómputos tardíos, cruzar al día siguiente. Usar ese campo para el día
    desplazaría la puntuación al día equivocado.

    Zepp reenvía el mismo día con el score recalculado varias veces según
    avanza (visto 2 actualizaciones el mismo día en 2/9 eventos, con
    ``rdnsScore``/``sleepHRV`` distintos cada vez); se conserva la de
    ``item.timestamp`` más alto por día.

    Centinela 255 -> None, en los tres campos estructurados y en ``extra``
    (resto de scores/baselines/insights: ahi, afib, skinTemp... — ver
    ``docs/zepp-api.md``). ``extra`` no se persiste todavía.
    """
    zone = ZoneInfo(tz)
    by_day: dict[str, dict] = {}
    for item in events_payload.get("items") or []:
        value = item.get("value") or {}
        day_anchor_ms = value.get("timestamp")
        if day_anchor_ms is None:
            continue
        day = datetime.fromtimestamp(day_anchor_ms / 1000, zone).date().isoformat()
        update_ms = item.get("timestamp", day_anchor_ms)

        existing = by_day.get(day)
        if existing is not None and existing["_update_ms"] >= update_ms:
            continue

        extra = {
            key: _readiness_sentinel_to_none(val)
            for key, val in value.items()
            if key not in _READINESS_CORE_KEYS and key not in _READINESS_META_KEYS
        }
        by_day[day] = {
            "_update_ms": update_ms,
            "day": day,
            "readiness": _readiness_sentinel_to_none(value.get("rdnsScore")),
            "sleepHRV": _readiness_sentinel_to_none(value.get("sleepHRV")),
            "sleepRHR": _readiness_sentinel_to_none(value.get("sleepRHR")),
            "extra": extra,
        }
    return [{k: v for k, v in entry.items() if k != "_update_ms"} for entry in by_day.values()]


def parse_all_day_stress(events_payload: dict, tz: str) -> list[dict]:
    """``all_day_stress`` (``/users/{id}/events``) -> un bloque por día cubierto.

    Cada bloque: ``{'day', 'start_ts', 'end_ts', 'samples', 'avg_stress'}``.
    ``samples`` = (ts_utc, valor 0-100); ``start_ts``/``end_ts`` acotan el día
    entero (se emitan muestras o no) porque la re-ingesta reemplaza ese rango
    completo (ver ``run.process_stress``).

    **Esta es la serie que PINTA la app.** El otro candidato, el blob
    ``stressInfo`` de ``Charge/stress_data``, se descartó: su parser (protobuf)
    llegó a funcionar pero producía una curva DENSA por minuto que no reproduce
    los huecos de la app (mejor R²=0.40) — es un modelo/agregado interno, no la
    medición. Aquí cada muestra trae su
    ``time`` en **epoch ms absoluto**: sin anclajes ni offsets. ``item.data`` es
    un **string JSON** de ``[{time, value}]`` (muestras dispersas y explícitas:
    los huecos de la app son, literalmente, minutos sin muestra). Los agregados
    del día viven a nivel de item (``avgStress``, ``maxStress``... como
    **strings**); se persiste ``avgStress`` en ``daily_metrics.stress_avg``.

    ``item.timestamp`` = medianoche UTC del día cubierto (múltiplo exacto de
    86400000); todas las muestras del item caen en ``[timestamp, timestamp+24h)``
    (verificado 7/7 días de crudo). El ``day`` se deriva en tz **LOCAL**: ``daily_metrics`` se indexa por día local (igual que
    ``parse_readiness``), así que ``avg_stress`` debe casar esa convención;
    ``start_ts``/``end_ts`` en cambio siguen anclados al instante UTC real de
    las muestras (definen el rango que reemplaza el DELETE de re-ingesta).

    **Cruce contra el ground truth de la app (2026-07-24)**: los tramos
    7:30-10:40 y 11:40-11:55 casan EXACTO (valor y huecos, 18/18 filas). El
    tramo 10:45-11:30 discrepa por un desplazamiento uniforme de +5 min que se
    reabsorbe al final: es un desliz de transcripción manual de la tabla, no del
    dato (28/28 aplicando ese +5 min a esa banda). Cotejo en vivo final
    PENDIENTE DE USUARIO.
    """
    zone = ZoneInfo(tz)
    blocks: list[dict] = []
    for item in events_payload.get("items") or []:
        ts_ms = item.get("timestamp")
        if ts_ms is None:
            continue
        start_ts = ts_ms // 1000
        day = datetime.fromtimestamp(start_ts, zone).date().isoformat()

        raw = item.get("data")
        if isinstance(raw, str):
            raw = json.loads(raw)
        samples: list[tuple[int, int]] = []
        for entry in raw or []:
            value = round(entry["value"])
            if not (_STRESS_MIN < value <= _STRESS_MAX):
                continue
            samples.append((entry["time"] // 1000, value))

        avg = item.get("avgStress")
        avg_stress = round(float(avg)) if avg not in (None, "") else None

        blocks.append(
            {
                "day": day,
                "start_ts": start_ts,
                "end_ts": start_ts + _STRESS_MINUTES_PER_DAY * 60,
                "samples": samples,
                "avg_stress": avg_stress,
            }
        )
    return blocks

