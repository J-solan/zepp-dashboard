"""Tests unitarios de ``ingest.parsers`` con inputs sintéticos mínimos.

Los tests de invariantes sobre payloads reales/sanitizados (fixtures/ y
fixtures_local/) viven en ``test_parsers_fixtures.py``.
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest import parsers

TZ = "Europe/Madrid"


def _band_day(date_time: str, hr_bytes: bytes = b"", summary_obj: dict | None = None) -> dict:
    summary_obj = {} if summary_obj is None else summary_obj
    return {
        "date_time": date_time,
        "data_hr": base64.b64encode(hr_bytes).decode(),
        "summary": base64.b64encode(json.dumps(summary_obj).encode()).decode(),
    }


# ---------------------------------------------------------------------------
# parse_hr_minute
# ---------------------------------------------------------------------------


def test_parse_hr_minute_discards_sentinel_zero_and_254():
    band_day = _band_day("2026-07-21", bytes([0, 254, 70]))
    result = parsers.parse_hr_minute(band_day, TZ)
    assert [bpm for _, bpm in result] == [70]


def test_parse_hr_minute_discards_out_of_range_even_if_not_sentinel():
    band_day = _band_day("2026-07-21", bytes([29, 30, 220, 221]))
    result = parsers.parse_hr_minute(band_day, TZ)
    assert [bpm for _, bpm in result] == [30, 220]


def test_parse_hr_minute_index_zero_is_local_midnight():
    band_day = _band_day("2026-07-21", bytes([60]))
    (ts, bpm), = parsers.parse_hr_minute(band_day, TZ)
    expected = int(datetime(2026, 7, 21, 0, 0, tzinfo=ZoneInfo(TZ)).timestamp())
    assert ts == expected
    assert bpm == 60


def test_parse_hr_minute_spring_forward_skips_missing_hour():
    # Europe/Madrid: 2026-03-29 salta de 02:00 a 03:00 (día de 23h).
    band_day = _band_day("2026-03-29", bytes([60] * 240))
    result = parsers.parse_hr_minute(band_day, TZ)
    ts_midnight = result[0][0]
    ts_index_180 = result[180][0]
    assert ts_index_180 - ts_midnight == 2 * 3600  # elapsed real = 2h, no 3h


def test_parse_hr_minute_fall_back_day_spans_25_real_hours():
    # Europe/Madrid: 2026-10-25 tiene 25h (repite la 02:00-03:00).
    band_day = _band_day("2026-10-25", bytes([60] * 1440))
    result = parsers.parse_hr_minute(band_day, TZ)
    ts_midnight = result[0][0]
    next_midnight = int(datetime(2026, 10, 26, 0, 0, tzinfo=ZoneInfo(TZ)).timestamp())
    assert next_midnight - ts_midnight == 25 * 3600


# ---------------------------------------------------------------------------
# parse_sleep
# ---------------------------------------------------------------------------


def _slp(**overrides):
    base = {
        "st": 1700000000,
        "ed": 1700003000,
        "ss": 77,
        "dp": 10,
        "lt": 20,
        "wk": 5,
        "wc": 1,
        "rhr": 50,
        "stage": [
            {"start": 0, "stop": 19, "mode": 4},   # ligero, 20 min -> lt
            {"start": 20, "stop": 29, "mode": 5},  # profundo, 10 min -> dp
            {"start": 30, "stop": 33, "mode": 8},  # REM, 4 min
            {"start": 34, "stop": 38, "mode": 7},  # despierto, 5 min -> wk
        ],
    }
    base.update(overrides)
    return base


def test_parse_sleep_session_fields_and_derived_rem_awake():
    band_day = _band_day("2026-07-21", summary_obj={"slp": _slp()})
    session, stages = parsers.parse_sleep(band_day, TZ)

    assert session["score"] == 77
    assert session["deep_min"] == 10
    assert session["light_min"] == 20
    assert session["rem_min"] == 4
    assert session["awake_min"] == 5
    assert session["wake_count"] == 1
    assert session["resting_hr"] == 50
    assert session["start_ts"] == 1700000000
    assert session["end_ts"] == 1700003000
    assert session["tz"] == TZ


def test_parse_sleep_stage_start_stop_are_inclusive_minutes_converted_to_utc():
    band_day = _band_day("2026-07-21", summary_obj={"slp": _slp()})
    _, stages = parsers.parse_sleep(band_day, TZ)

    assert len(stages) == 4
    ref = datetime(2026, 7, 20, 0, 0, tzinfo=ZoneInfo(TZ))  # medianoche de date_time - 1

    first = stages[0]
    assert first["stage"] == 4
    assert first["start_ts"] == int(ref.timestamp())
    assert first["end_ts"] == int(ref.timestamp()) + 20 * 60  # stop=19 inclusive -> +20 min

    rem = stages[2]
    assert rem["stage"] == 8
    assert rem["end_ts"] - rem["start_ts"] == 4 * 60


# ---------------------------------------------------------------------------
# parse_daily_from_band
# ---------------------------------------------------------------------------


def test_parse_daily_from_band_extracts_steps_and_calories():
    band_day = _band_day(
        "2026-07-21", summary_obj={"stp": {"ttl": 4310, "cal": 188, "dis": 3156}}
    )
    daily = parsers.parse_daily_from_band(band_day)
    assert daily == {"steps": 4310, "calories": 188}


def test_parse_daily_from_band_returns_none_without_stp_block():
    band_day = _band_day("2026-07-21", summary_obj={})
    assert parsers.parse_daily_from_band(band_day) is None


# ---------------------------------------------------------------------------
# parse_biocharge
# ---------------------------------------------------------------------------


def test_parse_biocharge_converts_ms_offset_to_utc_seconds():
    payload = {
        "items": [
            {
                "value": {
                    "startTime": 1700000000000,
                    "samples": [
                        {"s": 0, "total": 62, "mental": 42.1, "physical": 80.5, "status": 0},
                        {"s": 60000, "total": 63, "mental": 43.0, "physical": 81.0, "status": 0},
                    ],
                }
            }
        ]
    }
    result = parsers.parse_biocharge(payload)
    assert result == [
        (1700000000, 62, 42.1, 80.5, 0),
        (1700000060, 63, 43.0, 81.0, 0),
    ]


def test_parse_biocharge_nulls_total_sentinel_but_keeps_mental_and_physical():
    """255 en 'total' = fusion score aún no calculado; mental/physical siguen válidos."""
    payload = {
        "items": [
            {
                "value": {
                    "startTime": 1700000000000,
                    "samples": [
                        {"s": 0, "total": 63, "mental": 35.06, "physical": 90.80, "status": 0},
                        {"s": 60000, "total": 255, "mental": 35.02, "physical": 90.79, "status": 0},
                        {"s": 120000, "total": 255, "mental": 34.98, "physical": 90.78, "status": 0},
                        {"s": 180000, "total": 63, "mental": 34.94, "physical": 90.76, "status": 0},
                    ],
                }
            }
        ]
    }
    result = parsers.parse_biocharge(payload)
    assert result == [
        (1700000000, 63, 35.06, 90.80, 0),
        (1700000060, None, 35.02, 90.79, 0),
        (1700000120, None, 34.98, 90.78, 0),
        (1700000180, 63, 34.94, 90.76, 0),
    ]


# ---------------------------------------------------------------------------
# parse_respiratory
# ---------------------------------------------------------------------------


def _resp_item(measurements: bytes, timestamp_ms: int = 1784678400000, offset: int = 3600) -> dict:
    return {
        "timestamp": timestamp_ms,
        "value": {
            "measurements": base64.b64encode(measurements).decode(),
            "timeZone": [{"period": [0, len(measurements) - 1], "offset": offset}],
        },
    }


def test_parse_respiratory_discards_zero_sentinel():
    payload = {"items": [_resp_item(bytes([0, 17, 0, 18]))]}
    assert [rpm for _, rpm in parsers.parse_respiratory(payload)] == [17, 18]


def test_parse_respiratory_index_zero_is_utc_midnight_ignoring_offset():
    """El offset del payload es metadato: NO desplaza los ts (ver docstring)."""
    payload = {"items": [_resp_item(bytes([17, 18]), timestamp_ms=1784678400000, offset=3600)]}
    result = parsers.parse_respiratory(payload)
    assert result == [(1784678400, 17), (1784678460, 18)]
    assert datetime.fromtimestamp(result[0][0], timezone.utc).strftime("%H:%M") == "00:00"


def test_parse_respiratory_offset_changes_nothing():
    a = parsers.parse_respiratory({"items": [_resp_item(bytes([17]), offset=3600)]})
    b = parsers.parse_respiratory({"items": [_resp_item(bytes([17]), offset=7200)]})
    assert a == b


def test_parse_respiratory_cadence_is_one_sample_per_minute():
    payload = {"items": [_resp_item(bytes([16, 17, 18, 19]))]}
    ts = [t for t, _ in parsers.parse_respiratory(payload)]
    assert {b - a for a, b in zip(ts, ts[1:])} == {60}


def test_parse_respiratory_discards_out_of_range_values():
    payload = {"items": [_resp_item(bytes([3, 4, 60, 61]))]}
    assert [rpm for _, rpm in parsers.parse_respiratory(payload)] == [4, 60]


def test_parse_respiratory_skips_items_without_measurements():
    payload = {"items": [{"timestamp": 1784678400000, "value": {"timeZone": []}}]}
    assert parsers.parse_respiratory(payload) == []


# ---------------------------------------------------------------------------
# parse_daily_health
# ---------------------------------------------------------------------------


def test_parse_daily_health_uses_datestring_as_day():
    payload = {
        "items": [
            {
                "timestamp": 1784678400000,
                "value": {
                    "samples": [
                        {"s": 0, "dateString": "2026-07-22", "totalSteps": 2150, "totalCalories": 112}
                    ]
                },
            }
        ]
    }
    assert parsers.parse_daily_health(payload) == [
        {"day": "2026-07-22", "steps": 2150, "calories": 112}
    ]


def test_parse_daily_health_skips_samples_without_datestring():
    payload = {"items": [{"value": {"samples": [{"totalSteps": 10, "totalCalories": 1}]}}]}
    assert parsers.parse_daily_health(payload) == []


# ---------------------------------------------------------------------------
# parse_sport_load / parse_vo2max (WatchSportStatistics)
# ---------------------------------------------------------------------------


def test_parse_sport_load_prefers_the_daily_field():
    payload = {"items": [{"dayId": "2026-07-22", "wtlSum": 120, "currnetDayTrainLoad": 37}]}
    assert parsers.parse_sport_load(payload) == [("2026-07-22", 37)]


def test_parse_sport_load_skips_day_without_data_instead_of_using_weekly_sum():
    """-1 en el campo diario = ese día no tiene dato; wtlSum es OTRA métrica."""
    payload = {"items": [{"dayId": "2026-07-22", "wtlSum": 120, "currnetDayTrainLoad": -1}]}
    assert parsers.parse_sport_load(payload) == []


def test_parse_sport_load_falls_back_only_when_daily_field_is_absent():
    payload = {"items": [{"dayId": "2026-07-22", "wtlSum": 120}]}
    assert parsers.parse_sport_load(payload) == [("2026-07-22", 120)]


def test_parse_watch_statistics_normalises_numeric_dayid():
    payload = {"items": [{"dayId": 20260722, "currnetDayTrainLoad": 37}]}
    assert parsers.parse_sport_load(payload) == [("2026-07-22", 37)]


def test_parse_vo2max_reads_value_and_skips_sentinel():
    payload = {"items": [{"dayId": "2026-07-22", "vo2max": 47.5}, {"dayId": "2026-07-21", "vo2max": -1}]}
    assert parsers.parse_vo2max(payload) == [("2026-07-22", 47.5)]


def test_parse_watch_statistics_empty_payload():
    assert parsers.parse_sport_load({}) == []
    assert parsers.parse_vo2max({"items": []}) == []


# ---------------------------------------------------------------------------
# parse_sport_history
# ---------------------------------------------------------------------------

SPORT_TYPES = {"52": "fuerza", "122": "voley_playa", "223": "auto_ia"}


def _workout(**overrides):
    base = {
        "trackid": "1700000000",
        "source": "run.1000001.huami.com",
        "end_time": "1700003600",
        "run_time": "3600",
        "type": 52,
        "avg_heart_rate": "118.0",
        "max_heart_rate": 154,
        "min_heart_rate": 82,
        "calorie": "300.0",
        "exercise_load": 29,
        "te": 21,
        "heart_range": "249,98;1943,118",
        "strengthScores": "[85,79.7]",
        "auto_recognition": False,
        "syncedTimezone": "Europe/Madrid",
        "sport_title": "",
    }
    base.update(overrides)
    return base


def _payload(*workouts):
    return {"data": {"summary": list(workouts)}}


def test_parse_sport_history_scales_te_and_marks_auto_for_known_code():
    workouts = parsers.parse_sport_history(_payload(_workout()), SPORT_TYPES)
    assert len(workouts) == 1
    w = workouts[0]
    assert w["te"] == 2.1
    assert w["review_status"] == "auto"
    assert w["trackid"] == 1700000000
    assert w["end_time"] == 1700003600
    assert w["run_time"] == 3600
    assert w["avg_heart_rate"] == 118.0
    assert w["max_heart_rate"] == 154
    assert w["min_heart_rate"] == 82
    assert w["calorie"] == 300.0
    assert w["exercise_load"] == 29
    assert w["heart_range"] == "249,98;1943,118"
    assert w["strengthScores"] == "[85,79.7]"
    assert w["auto_recognition"] is False


def test_parse_sport_history_keeps_the_title_the_user_typed_in_the_app():
    """``sport_title`` es el nombre que el usuario le puso en Zepp ("Bici
    trabajo"): pre-rellena el título en vez de preguntarle otra vez."""
    w = parsers.parse_sport_history(_payload(_workout(sport_title="Bici trabajo ")), SPORT_TYPES)[0]
    assert w["sport_title"] == "Bici trabajo"


def test_parse_sport_history_empty_title_is_none_not_empty_string():
    """Viene '' la mayoría de las veces; None es lo que deja pasar al título de
    la fuente al ``or`` que resuelve el efectivo."""
    assert parsers.parse_sport_history(_payload(_workout()), SPORT_TYPES)[0]["sport_title"] is None
    w = _workout()
    del w["sport_title"]
    assert parsers.parse_sport_history(_payload(w), SPORT_TYPES)[0]["sport_title"] is None


def test_parse_sport_history_type_223_is_always_pending():
    workouts = parsers.parse_sport_history(_payload(_workout(type=223)), SPORT_TYPES)
    assert workouts[0]["review_status"] == "pending"


def test_parse_sport_history_unknown_code_is_pending():
    workouts = parsers.parse_sport_history(_payload(_workout(type=999)), SPORT_TYPES)
    assert workouts[0]["review_status"] == "pending"


def test_parse_sport_history_sentinels_become_none():
    workout = _workout(
        avg_heart_rate="-1.0",
        max_heart_rate=-1,
        min_heart_rate=-1,
        calorie="-1.0",
        exercise_load=-1,
        te=-1,
    )
    w = parsers.parse_sport_history(_payload(workout), SPORT_TYPES)[0]
    assert w["avg_heart_rate"] is None
    assert w["max_heart_rate"] is None
    assert w["min_heart_rate"] is None
    assert w["calorie"] is None
    assert w["exercise_load"] is None
    assert w["te"] is None


# ---------------------------------------------------------------------------
# parse_readiness
# ---------------------------------------------------------------------------


def _readiness_item(value_timestamp_ms: int, item_timestamp_ms: int, **value_overrides) -> dict:
    value = {
        "rdnsScore": 81,
        "sleepHRV": 75,
        "sleepRHR": 50,
        "hrvScore": 81,
        "ahiScore": 100,
        "afibScore": 255,
        "skinTempScore": 99,
        "rhrScore": 100,
        "timestamp": value_timestamp_ms,
        "timestampUpdate": item_timestamp_ms,
        "timezoneId": TZ,
        "status": 200,
        "algVer": 4,
        "algSubVer": 3,
        "deviceId": "SYNTHDEV0001",
        "deviceSource": 1000001,
        "insightId": 1,
    }
    value.update(value_overrides)
    return {
        "userId": "1",
        "eventType": "readiness",
        "subType": "watch_score",
        "timestamp": item_timestamp_ms,
        "value": value,
    }


def _local_midnight_ms(day: date, tz: str = TZ) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def test_parse_readiness_day_comes_from_value_timestamp_not_item_timestamp():
    # value.timestamp = medianoche local del 22; item.timestamp (actualización
    # tardía) ya cae pasada la medianoche del 23. Debe seguir siendo día 22.
    value_ts = _local_midnight_ms(date(2026, 7, 22))
    item_ts = int(datetime(2026, 7, 23, 0, 30, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)
    payload = {"items": [_readiness_item(value_ts, item_ts)]}

    result = parsers.parse_readiness(payload, TZ)

    assert [r["day"] for r in result] == ["2026-07-22"]


def test_parse_readiness_extracts_core_fields():
    value_ts = _local_midnight_ms(date(2026, 7, 22))
    payload = {"items": [_readiness_item(value_ts, value_ts, rdnsScore=81, sleepHRV=75, sleepRHR=50)]}

    result = parsers.parse_readiness(payload, TZ)[0]

    assert result["readiness"] == 81
    assert result["sleepHRV"] == 75
    assert result["sleepRHR"] == 50


def test_parse_readiness_sentinel_255_becomes_none():
    value_ts = _local_midnight_ms(date(2026, 7, 22))
    payload = {
        "items": [
            _readiness_item(value_ts, value_ts, rdnsScore=255, sleepHRV=255, sleepRHR=255, afibScore=255)
        ]
    }

    result = parsers.parse_readiness(payload, TZ)[0]

    assert result["readiness"] is None
    assert result["sleepHRV"] is None
    assert result["sleepRHR"] is None
    assert result["extra"]["afibScore"] is None


def test_parse_readiness_keeps_latest_update_per_day():
    value_ts = _local_midnight_ms(date(2026, 7, 22))
    early = _readiness_item(value_ts, value_ts + 3 * 3600 * 1000, rdnsScore=58, sleepHRV=77)
    late = _readiness_item(value_ts, value_ts + 8 * 3600 * 1000, rdnsScore=59, sleepHRV=81)
    payload = {"items": [early, late]}

    result = parsers.parse_readiness(payload, TZ)

    assert len(result) == 1
    assert result[0]["readiness"] == 59
    assert result[0]["sleepHRV"] == 81


def test_parse_readiness_extra_dict_holds_secondary_scores_without_duplicating_core():
    value_ts = _local_midnight_ms(date(2026, 7, 22))
    payload = {"items": [_readiness_item(value_ts, value_ts, ahiScore=100, hrvScore=81)]}

    extra = parsers.parse_readiness(payload, TZ)[0]["extra"]

    assert extra["ahiScore"] == 100
    assert extra["hrvScore"] == 81
    assert "rdnsScore" not in extra
    assert "sleepHRV" not in extra
    assert "sleepRHR" not in extra


# ---------------------------------------------------------------------------
# parse_all_day_stress (fuente real de la app)
# ---------------------------------------------------------------------------


def _all_day_item(timestamp_ms: int, samples: list[tuple[int, int]], **extra) -> dict:
    """item de all_day_stress: ``data`` es un STRING JSON de [{time, value}]."""
    data = [{"time": ts_ms, "value": v} for ts_ms, v in samples]
    return {"timestamp": timestamp_ms, "data": json.dumps(data), **extra}


def test_parse_all_day_stress_reads_absolute_timestamps():
    """time es epoch ms absoluto -> ts_utc directo, sin anclajes."""
    ts0 = 1784851200000  # medianoche UTC 2026-07-24
    payload = {"items": [_all_day_item(ts0, [(ts0, 46), (ts0 + 5 * 60000, 9)])]}

    blocks = parsers.parse_all_day_stress(payload, TZ)

    assert len(blocks) == 1
    assert blocks[0]["samples"] == [(ts0 // 1000, 46), (ts0 // 1000 + 300, 9)]


def test_parse_all_day_stress_samples_are_sparse_with_gaps():
    """Las muestras son explícitas: un minuto sin muestra es un hueco (no se rellena)."""
    ts0 = 1784851200000
    # 7:30 y 7:45 con dato, 7:35/7:40 sin muestra (huecos de la app)
    payload = {
        "items": [_all_day_item(ts0, [(ts0 + 450 * 60000, 44), (ts0 + 465 * 60000, 47)])]
    }

    samples = parsers.parse_all_day_stress(payload, TZ)[0]["samples"]

    assert samples == [(ts0 // 1000 + 450 * 60, 44), (ts0 // 1000 + 465 * 60, 47)]


def test_parse_all_day_stress_exposes_the_day_aggregate():
    ts0 = 1784851200000
    payload = {"items": [_all_day_item(ts0, [(ts0, 30)], avgStress="28")]}

    block = parsers.parse_all_day_stress(payload, TZ)[0]

    assert block["avg_stress"] == 28
    assert block["day"] == "2026-07-24"
    assert block["start_ts"] == ts0 // 1000
    assert block["end_ts"] == ts0 // 1000 + 86400


def test_parse_all_day_stress_day_uses_local_tz_not_utc():
    """``daily_metrics`` se indexa por día LOCAL (patrón
    ``parse_readiness``/``todayISO``). ``item.timestamp`` es medianoche UTC; en
    un tz de offset negativo ese instante cae el día anterior, y el ``day`` debe
    reflejar el LOCAL, no el UTC."""
    ts0 = 1784851200000  # medianoche UTC del 2026-07-24
    payload = {"items": [_all_day_item(ts0, [(ts0, 40)], avgStress="30")]}

    # America/New_York (UTC-4 en verano): ese instante es 2026-07-23 20:00 local.
    block = parsers.parse_all_day_stress(payload, "America/New_York")[0]
    assert block["day"] == "2026-07-23"
    # el rango del DELETE sigue anclado al instante real de las muestras (UTC).
    assert block["start_ts"] == ts0 // 1000


def test_parse_all_day_stress_discards_out_of_range_values():
    ts0 = 1784851200000
    payload = {
        "items": [_all_day_item(ts0, [(ts0, 0), (ts0 + 60000, 45), (ts0 + 120000, 150)])]
    }

    samples = parsers.parse_all_day_stress(payload, TZ)[0]["samples"]

    assert samples == [(ts0 // 1000 + 60, 45)]


def test_parse_all_day_stress_empty_day_still_reports_the_range():
    """Un día sin muestras emite bloque con rango (lo usa el DELETE) y avg None."""
    ts0 = 1784851200000
    payload = {"items": [_all_day_item(ts0, [])]}

    assert parsers.parse_all_day_stress(payload, TZ) == [
        {
            "day": "2026-07-24",
            "start_ts": ts0 // 1000,
            "end_ts": ts0 // 1000 + 86400,
            "samples": [],
            "avg_stress": None,
        }
    ]


# ---------------------------------------------------------------------------
# parse_naps (odd_stage)
# ---------------------------------------------------------------------------


def _with_naps(odd_stage: list[dict]) -> dict:
    return _band_day("2026-07-21", summary_obj={"slp": {**_slp(), "odd_stage": odd_stage}})


def test_parse_naps_groups_contiguous_segments_into_one_nap():
    """Un tramo 'despierto' EN MEDIO no parte la siesta: se han visto huecos
    despierto de 11 min dentro de una sola siesta."""
    naps = parsers.parse_naps(
        _with_naps([
            {"start": 1000, "stop": 1017, "mode": 4},
            {"start": 1018, "stop": 1028, "mode": 7},
            {"start": 1029, "stop": 1051, "mode": 4},
        ]),
        TZ,
    )
    assert len(naps) == 1
    session, stages = naps[0]
    assert len(stages) == 3
    assert session["light_min"] == 18 + 23
    assert session["awake_min"] == 11
    assert session["end_ts"] - session["start_ts"] == 52 * 60


def test_parse_naps_splits_on_a_real_gap():
    """Cinco tramos separados por horas son cinco siestas, no una de 10 h."""
    naps = parsers.parse_naps(
        _with_naps([
            {"start": 769, "stop": 799, "mode": 4},    # 12:49
            {"start": 888, "stop": 922, "mode": 4},    # 14:48, 89 min después
        ]),
        TZ,
    )
    assert len(naps) == 2
    assert [s["light_min"] for s, _ in naps] == [31, 35]


def test_parse_naps_have_no_score_nor_resting_hr():
    """ss/rhr/wc son del sueño nocturno; una siesta no los trae."""
    session, _ = parsers.parse_naps(_with_naps([{"start": 800, "stop": 820, "mode": 4}]), TZ)[0]
    assert session["score"] is None
    assert session["resting_hr"] is None
    assert session["wake_count"] is None
    assert session["is_nap"] == 1


def test_parse_naps_derive_deep_and_rem_when_present():
    session, _ = parsers.parse_naps(
        _with_naps([
            {"start": 800, "stop": 813, "mode": 4},
            {"start": 814, "stop": 831, "mode": 5},
            {"start": 832, "stop": 835, "mode": 8},
        ]),
        TZ,
    )[0]
    assert (session["light_min"], session["deep_min"], session["rem_min"]) == (14, 18, 4)


def test_parse_naps_is_anchored_like_stage_the_day_before():
    session, _ = parsers.parse_naps(_with_naps([{"start": 2209, "stop": 2239, "mode": 4}]), TZ)[0]
    # 2209 min desde la medianoche del 20-jul = 21-jul a las 12:49 locales.
    assert datetime.fromtimestamp(session["start_ts"], ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M") == "2026-07-21 12:49"


def test_parse_naps_returns_nothing_without_odd_stage():
    assert parsers.parse_naps(_band_day("2026-07-21", summary_obj={"slp": _slp()}), TZ) == []


def test_night_session_is_not_a_nap():
    session, _ = parsers.parse_sleep(_band_day("2026-07-21", summary_obj={"slp": _slp()}), TZ)
    assert session["is_nap"] == 0


def test_parse_naps_ignores_unknown_stage_mode_in_totals():
    """Un mode fuera de 4/5/7/8 no debe colarse como clave nueva del dict de
    minutos: los cuatro totales documentados no deben moverse."""
    session, stages = parsers.parse_naps(
        _with_naps([
            {"start": 800, "stop": 813, "mode": 4},
            {"start": 814, "stop": 820, "mode": 99},
        ]),
        TZ,
    )[0]
    assert (session["light_min"], session["deep_min"], session["rem_min"], session["awake_min"]) == (14, 0, 0, 0)
    assert len(stages) == 2  # el tramo desconocido sigue en el hipnograma crudo
