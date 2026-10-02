"""Invariantes de los parsers sobre payloads reales de fixture.

Corre siempre sobre ``fixtures/`` (sanitizadas, versionadas, usadas en CI) y,
si hay payloads reales, también sobre ``fixtures_local/`` (skip limpio si el
directorio está vacío o solo tiene el README).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from ingest import parsers
from ingest.config import load_config

FIXTURES_ROOT = Path(__file__).parent
TZ = "Europe/Madrid"
SPORT_TYPES = {"52": "fuerza", "122": "voley_playa", "223": "auto_ia"}


def _dir_has_data(dir_path: Path) -> bool:
    return dir_path.exists() and any(p.name != "README.md" for p in dir_path.iterdir())


def _real_identifiers() -> list[str]:
    """Identificadores de TU cuenta, leídos de tus payloads reales y tu config.

    No se escriben aquí: este fichero se publica, y una lista literal sería
    justo la fuga que el test intenta impedir. Sin ``fixtures_local/`` ni
    config (CI, un clon ajeno) no hay nada con qué comparar.
    """
    ids: set[str] = set()
    local = FIXTURES_ROOT / "fixtures_local"
    if _dir_has_data(local):
        band = json.loads((local / "band_data_day.json").read_text())["data"][0]
        sport = json.loads((local / "sport_history.json").read_text())["data"]["summary"][0]
        charge = json.loads((local / "biocharge_day.json").read_text())["items"][0]
        ids |= {
            band["uid"],
            str(band["source"]),
            band["device_id"],
            band["uuid"],
            sport["deviceid"],
            sport["sn"],
            sport["devicesource"],
            charge["userId"],
        }
    email = load_config(required=False).get("email")
    if email:
        ids.add(email)
    return sorted(i for i in ids if i)


def _load(dir_name: str, filename: str) -> dict:
    dir_path = FIXTURES_ROOT / dir_name
    if not _dir_has_data(dir_path):
        pytest.skip(f"{dir_name}/ vacío (solo README) — se omite")
    return json.loads((dir_path / filename).read_text())


DIRS = ["fixtures", "fixtures_local"]


@pytest.mark.parametrize("dir_name", DIRS)
def test_hr_minute_in_range_without_sentinels(dir_name):
    band = _load(dir_name, "band_data_day.json")
    found_any = False
    for day in band["data"]:
        result = parsers.parse_hr_minute(day, TZ)
        assert result, "se esperaban muestras de FC válidas"
        for ts, bpm in result:
            assert 30 <= bpm <= 220
            found_any = True
    assert found_any


@pytest.mark.parametrize("dir_name", DIRS)
def test_sleep_stage_sums_match_dp_lt_and_rem(dir_name):
    band = _load(dir_name, "band_data_day.json")
    for day in band["data"]:
        session, stages = parsers.parse_sleep(day, TZ)
        light = sum((s["end_ts"] - s["start_ts"]) // 60 for s in stages if s["stage"] == 4)
        deep = sum((s["end_ts"] - s["start_ts"]) // 60 for s in stages if s["stage"] == 5)
        rem = sum((s["end_ts"] - s["start_ts"]) // 60 for s in stages if s["stage"] == 8)
        assert abs(light - session["light_min"]) <= 1
        assert abs(deep - session["deep_min"]) <= 1
        assert rem == session["rem_min"]


@pytest.mark.parametrize("dir_name", DIRS)
def test_biocharge_cadence_and_range(dir_name):
    payload = _load(dir_name, "biocharge_day.json")
    result = parsers.parse_biocharge(payload)
    assert len(result) > 1
    diffs = {b[0] - a[0] for a, b in zip(result, result[1:])}
    assert diffs == {60}, f"cadencia esperada ~1/min, diffs vistos: {diffs}"
    for _, total, mental, physical, status in result:
        assert 0 <= total <= 100


@pytest.mark.parametrize("dir_name", DIRS)
def test_sport_history_223_pending_and_known_codes_auto(dir_name):
    """Invariante universal: 223 siempre 'pending'; code conocido != 223 -> 'auto'."""
    payload = _load(dir_name, "sport_history.json")
    workouts = parsers.parse_sport_history(payload, SPORT_TYPES)
    assert workouts

    by_type: dict[int, list[dict]] = {}
    for w in workouts:
        by_type.setdefault(w["type"], []).append(w)

    assert all(w["review_status"] == "pending" for w in by_type.get(223, []))
    for sport_type, group in by_type.items():
        if sport_type != 223 and str(sport_type) in SPORT_TYPES:
            assert all(w["review_status"] == "auto" for w in group)


def test_sanitized_sport_history_has_unknown_code_and_sentinels():
    """Casos sintéticos garantizados solo en fixtures/ (la cuenta real no
    tiene codes fuera de mapa ni métricas centinela en esta muestra)."""
    payload = _load("fixtures", "sport_history.json")
    workouts = parsers.parse_sport_history(payload, SPORT_TYPES)

    unknown = [w for w in workouts if str(w["type"]) not in SPORT_TYPES]
    assert unknown, "se esperaba al menos un workout con code fuera del mapa sport_types"
    assert all(w["review_status"] == "pending" for w in unknown)

    assert any(
        w["avg_heart_rate"] is None
        or w["max_heart_rate"] is None
        or w["min_heart_rate"] is None
        or w["calorie"] is None
        or w["exercise_load"] is None
        or w["te"] is None
        for w in workouts
    )


@pytest.mark.parametrize("dir_name", DIRS)
def test_all_output_timestamps_are_unix_seconds(dir_name):
    band = _load(dir_name, "band_data_day.json")
    for day in band["data"]:
        hr = parsers.parse_hr_minute(day, TZ)
        session, stages = parsers.parse_sleep(day, TZ)
        for ts, _ in hr:
            assert 10**9 < ts < 10**10
        assert 10**9 < session["start_ts"] < 10**10
        assert 10**9 < session["end_ts"] < 10**10
        for stage in stages:
            assert 10**9 < stage["start_ts"] < 10**10
            assert 10**9 < stage["end_ts"] < 10**10

    biocharge = _load(dir_name, "biocharge_day.json")
    for ts, *_ in parsers.parse_biocharge(biocharge):
        assert 10**9 < ts < 10**10

    sport = _load(dir_name, "sport_history.json")
    for w in parsers.parse_sport_history(sport, SPORT_TYPES):
        assert 10**9 < w["trackid"] < 10**10
        assert 10**9 < w["end_time"] < 10**10


def test_sanitized_data_hr_contains_sentinel_bytes():
    band = _load("fixtures", "band_data_day.json")
    for day in band["data"]:
        raw = base64.b64decode(day["data_hr"])
        assert any(b in (0, 254) for b in raw), "el data_hr sanitizado debe conservar centinelas"


def test_fixtures_do_not_contain_real_identifiers():
    real = _real_identifiers()
    if not real:
        pytest.skip("sin fixtures_local/ ni config: no hay identificadores reales que buscar")
    for path in (FIXTURES_ROOT / "fixtures").glob("*.json"):
        text = path.read_text()
        for rid in real:
            # pytest.fail y no assert: la reescritura de asserts imprimiría el identificador real en la salida.
            if rid in text:
                pytest.fail(f"identificador real filtrado en {path.name}", pytrace=False)


def test_sanitized_series_are_not_byte_identical_to_real():
    if not _dir_has_data(FIXTURES_ROOT / "fixtures_local"):
        pytest.skip("fixtures_local/ vacío — no hay series reales con las que comparar")

    real_band = _load("fixtures_local", "band_data_day.json")
    fake_band = _load("fixtures", "band_data_day.json")
    assert real_band["data"][0]["data_hr"] != fake_band["data"][0]["data_hr"]
    assert real_band["data"][0]["summary"] != fake_band["data"][0]["summary"]

    real_charge = _load("fixtures_local", "biocharge_day.json")
    fake_charge = _load("fixtures", "biocharge_day.json")
    assert (
        real_charge["items"][0]["value"]["samples"]
        != fake_charge["items"][0]["value"]["samples"]
    )

    real_sport = _load("fixtures_local", "sport_history.json")
    fake_sport = _load("fixtures", "sport_history.json")
    assert real_sport["data"]["summary"] != fake_sport["data"]["summary"]
