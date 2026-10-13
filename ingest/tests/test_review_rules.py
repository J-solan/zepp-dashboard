"""Tests de ``ingest.review_rules``: validación de las reglas del config y sugerencia.

Los entrenos son dicts con las columnas que mira ``suggest`` (las mismas que una
fila de ``workout``); las fechas y cifras son inventadas.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ingest.review_rules import compile_rules, suggest

TZ = "Europe/Madrid"


def workout(local: str, minutes: float = 45, load: int | None = 10, code: int = 223) -> dict:
    """Entreno que empieza a ``local`` ('YYYY-MM-DD HH:MM', hora de Madrid)."""
    start = int(datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(TZ)).timestamp())
    return {"start_ts": start, "end_ts": start + int(minutes * 60), "train_load": load, "sport_type": code}


def suggested(w: dict, *rules: dict) -> dict | None:
    return suggest(w, compile_rules(list(rules)), TZ)


# 2026-03-02 es lunes.
MONDAY = "2026-03-02"


# ---------------------------------------------------------------------------
# Sugerencia
# ---------------------------------------------------------------------------


def test_no_rules_no_suggestion():
    assert suggested(workout(f"{MONDAY} 10:00")) is None


def test_a_rule_without_conditions_matches_everything():
    assert suggested(workout(f"{MONDAY} 10:00"), {"sport": "yoga"}) == {
        "action": "classify",
        "sport": "yoga",
        "rule": None,
    }


def test_ignore_rule_suggests_discarding_with_its_name():
    assert suggested(workout(f"{MONDAY} 10:00"), {"name": "Ruido", "ignore": True}) == {
        "action": "ignore",
        "rule": "Ruido",
    }


def test_the_first_matching_rule_wins():
    w = workout(f"{MONDAY} 06:30", minutes=40)
    rules = (
        {"name": "Corto", "ignore": True, "minutes": [0, 4]},
        {"name": "Natación", "sport": "natacion", "start": ["06:00", "07:45"]},
        {"name": "Todo", "sport": "yoga"},
    )
    assert suggested(w, *rules)["rule"] == "Natación"


def test_minutes_are_inclusive_on_both_ends():
    rule = {"ignore": True, "minutes": [10, 20]}
    assert suggested(workout(f"{MONDAY} 10:00", minutes=10), rule)
    assert suggested(workout(f"{MONDAY} 10:00", minutes=20), rule)
    assert suggested(workout(f"{MONDAY} 10:00", minutes=20.5), rule) is None
    assert suggested(workout(f"{MONDAY} 10:00", minutes=9.5), rule) is None


def test_start_window_uses_the_local_hour_of_the_config_tz():
    rule = {"sport": "natacion", "start": ["06:00", "07:45"]}
    assert suggested(workout(f"{MONDAY} 06:00"), rule)
    assert suggested(workout(f"{MONDAY} 07:45"), rule)
    assert suggested(workout(f"{MONDAY} 07:46"), rule) is None
    # 06:30 en Madrid son las 05:30 UTC: si se mirara la hora UTC no encajaría.
    assert suggest(workout(f"{MONDAY} 06:30"), compile_rules([rule]), "UTC") is None


def test_start_window_can_cross_midnight():
    rule = {"sport": "guardia", "start": ["22:15", "01:30"]}
    assert suggested(workout(f"{MONDAY} 22:15"), rule)
    assert suggested(workout(f"{MONDAY} 23:59"), rule)
    assert suggested(workout(f"{MONDAY} 00:40"), rule)
    assert suggested(workout(f"{MONDAY} 01:30"), rule)
    assert suggested(workout(f"{MONDAY} 12:00"), rule) is None


def test_weekdays_count_from_monday_as_one():
    rule = {"sport": "yoga", "weekdays": [1, 7]}
    assert suggested(workout(f"{MONDAY} 10:00"), rule)
    assert suggested(workout("2026-03-08 10:00"), rule)  # domingo
    assert suggested(workout("2026-03-03 10:00"), rule) is None  # martes


def test_months():
    rule = {"sport": "esqui", "months": [12, 1, 2]}
    assert suggested(workout("2026-02-10 10:00"), rule)
    assert suggested(workout(f"{MONDAY} 10:00"), rule) is None


def test_max_load_counts_a_missing_load_as_zero():
    rule = {"ignore": True, "max_load": 5}
    assert suggested(workout(f"{MONDAY} 10:00", load=5), rule)
    assert suggested(workout(f"{MONDAY} 10:00", load=None), rule)
    assert suggested(workout(f"{MONDAY} 10:00", load=6), rule) is None


def test_codes():
    rule = {"sport": "remo", "codes": [223, 901]}
    assert suggested(workout(f"{MONDAY} 10:00", code=901), rule)
    assert suggested(workout(f"{MONDAY} 10:00", code=52), rule) is None


def test_conditions_combine_with_and():
    rule = {"sport": "natacion", "start": ["06:00", "07:45"], "weekdays": [1], "minutes": [30, 60]}
    assert suggested(workout(f"{MONDAY} 06:30", minutes=40), rule)
    assert suggested(workout(f"{MONDAY} 06:30", minutes=90), rule) is None
    assert suggested(workout("2026-03-03 06:30", minutes=40), rule) is None


def test_a_workout_without_times_only_matches_rules_without_time_conditions():
    w = {"start_ts": None, "end_ts": None, "train_load": None, "sport_type": 223}
    assert suggested(w, {"ignore": True, "minutes": [0, 4]}, {"sport": "yoga", "codes": [223]}) == {
        "action": "classify",
        "sport": "yoga",
        "rule": None,
    }


# ---------------------------------------------------------------------------
# Validación: una errata nunca se ignora en silencio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ({"sport": "yoga", "minute": [1, 2]}, r"review_rules\[0\]\.minute: clave desconocida"),
        ({"name": "x"}, r"review_rules\[0\]: falta 'sport' o 'ignore = true'"),
        ({"sport": "yoga", "ignore": True}, r"review_rules\[0\]: 'sport' e 'ignore' a la vez"),
        ({"ignore": False}, r"review_rules\[0\]\.ignore: solo admite true"),
        ({"sport": ""}, r"review_rules\[0\]\.sport: "),
        ({"sport": 3}, r"review_rules\[0\]\.sport: "),
        ({"sport": "yoga", "name": 3}, r"review_rules\[0\]\.name: "),
        ({"sport": "yoga", "minutes": 10}, r"review_rules\[0\]\.minutes: "),
        ({"sport": "yoga", "minutes": [10]}, r"review_rules\[0\]\.minutes: "),
        ({"sport": "yoga", "minutes": ["5", 10]}, r"review_rules\[0\]\.minutes: "),
        ({"sport": "yoga", "minutes": [20, 10]}, r"review_rules\[0\]\.minutes: "),
        ({"sport": "yoga", "start": ["6:00", "07:45"]}, r"review_rules\[0\]\.start: "),
        ({"sport": "yoga", "start": ["06:00", "24:00"]}, r"review_rules\[0\]\.start: "),
        ({"sport": "yoga", "start": ["06:00", "07:60"]}, r"review_rules\[0\]\.start: "),
        ({"sport": "yoga", "start": "06:00"}, r"review_rules\[0\]\.start: "),
        ({"sport": "yoga", "weekdays": [0]}, r"review_rules\[0\]\.weekdays: "),
        ({"sport": "yoga", "weekdays": [8]}, r"review_rules\[0\]\.weekdays: "),
        ({"sport": "yoga", "weekdays": []}, r"review_rules\[0\]\.weekdays: "),
        ({"sport": "yoga", "weekdays": [True]}, r"review_rules\[0\]\.weekdays: "),
        ({"sport": "yoga", "months": [13]}, r"review_rules\[0\]\.months: "),
        ({"sport": "yoga", "max_load": "10"}, r"review_rules\[0\]\.max_load: "),
        ({"sport": "yoga", "max_load": True}, r"review_rules\[0\]\.max_load: "),
        ({"sport": "yoga", "codes": ["223"]}, r"review_rules\[0\]\.codes: "),
    ],
)
def test_malformed_rules_are_rejected_naming_the_rule_and_the_key(rule, message):
    with pytest.raises(ValueError, match=message):
        compile_rules([rule])


def test_the_error_points_at_the_right_rule():
    with pytest.raises(ValueError, match=r"review_rules\[1\]\.strat"):
        compile_rules([{"sport": "yoga"}, {"ignore": True, "strat": ["06:00", "06:45"]}])


def test_review_rules_must_be_a_list_of_tables():
    with pytest.raises(ValueError, match="review_rules"):
        compile_rules({"sport": "yoga"})
    with pytest.raises(ValueError, match=r"review_rules\[0\]"):
        compile_rules(["yoga"])


def test_float_minutes_and_load_are_accepted():
    assert compile_rules([{"ignore": True, "minutes": [0, 4.5], "max_load": 2.5}])
