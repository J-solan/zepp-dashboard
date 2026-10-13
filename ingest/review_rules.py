"""Reglas de la cola de revisión: SUGIEREN qué fue un entreno pendiente, nunca lo aplican.

Se escriben en ``ingest/config.toml`` como una lista ``[[review_rules]]`` (ver
``ingest/config.example.toml``) y la API añade con ellas una ``suggestion`` a
cada pendiente; aplicarla es un clic del usuario por el endpoint de revisión de
siempre. Sugerir y no aplicar es a propósito: una regla es una heurística ("lo
de primera hora entre semana es natación"), y un falso positivo aplicado solo
se quedaría escondido en el histórico sin que nadie lo mirara.

Funciones PURAS, sin red ni BBDD. El entreno es cualquier mapping con
``start_ts``/``end_ts``/``train_load``/``sport_type``: una fila de ``workout``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

KEYS = ("name", "sport", "ignore", "minutes", "start", "weekdays", "months", "max_load", "codes")
_HHMM = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


def _number(value: Any) -> bool:
    # bool es subclase de int: sin esto ``max_load = true`` pasaría por un 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _ints(value: Any, low: int | None = None, high: int | None = None) -> bool:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(
            isinstance(v, int) and not isinstance(v, bool) and (low is None or low <= v <= high)
            for v in value
        )
    )


def _pair(value: Any, item_ok) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(item_ok(v) for v in value)


# Clave -> (es válido, cómo debería ser). ``name``/``sport``/``ignore`` van aparte.
_CONDITIONS = {
    "minutes": (lambda v: _pair(v, _number) and v[0] <= v[1], "[mín, máx] en minutos, con mín <= máx"),
    "start": (
        lambda v: _pair(v, lambda t: isinstance(t, str) and _HHMM.fullmatch(t)),
        '["HH:MM", "HH:MM"] (00:00 a 23:59)',
    ),
    "weekdays": (lambda v: _ints(v, 1, 7), "una lista de días, 1 = lunes … 7 = domingo"),
    "months": (lambda v: _ints(v, 1, 12), "una lista de meses, 1-12"),
    "max_load": (_number, "un número"),
    "codes": (_ints, "una lista de sport codes (números)"),
}


def compile_rules(raw: Any) -> list[dict[str, Any]]:
    """Valida ``review_rules`` del config y la deja lista para ``suggest``.

    Cualquier cosa rara es un ``ValueError`` que nombra la regla y la clave, y
    la API no arranca. Ignorarla en silencio sería peor que no tener reglas: una
    condición mal escrita que se descarta deja la regla en "encaja con todo", y
    si va primera, toda la cola sale sugerida como eso.
    """
    if not isinstance(raw, list):
        raise ValueError("review_rules: debe ser una lista de tablas [[review_rules]]")
    return [_compile(f"review_rules[{i}]", rule) for i, rule in enumerate(raw)]


def _compile(where: str, rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise ValueError(f"{where}: debe ser una tabla [[review_rules]]")
    for key in rule:
        if key not in KEYS:
            raise ValueError(f"{where}.{key}: clave desconocida (válidas: {', '.join(KEYS)})")
    if "ignore" in rule and rule["ignore"] is not True:
        raise ValueError(f"{where}.ignore: solo admite true")
    if "sport" in rule and "ignore" in rule:
        raise ValueError(f"{where}: 'sport' e 'ignore' a la vez; elige una de las dos")
    if "sport" not in rule and "ignore" not in rule:
        raise ValueError(f"{where}: falta 'sport' o 'ignore = true'")
    for key in ("sport", "name"):
        if key in rule and not (isinstance(rule[key], str) and rule[key].strip()):
            raise ValueError(f"{where}.{key}: debe ser un texto no vacío, no {rule[key]!r}")
    for key, (ok, expected) in _CONDITIONS.items():
        if key in rule and not ok(rule[key]):
            raise ValueError(f"{where}.{key}: debe ser {expected}, no {rule[key]!r}")

    compiled = dict(rule)
    if "start" in rule:
        compiled["start"] = tuple(int(t[:2]) * 60 + int(t[3:]) for t in rule["start"])
    return compiled


def suggest(workout: Mapping[str, Any], rules: list[dict[str, Any]], tz: str) -> dict[str, Any] | None:
    """Sugerencia de la PRIMERA regla que encaje, o ``None``.

    ``{"action": "classify", "sport": ..., "rule": name}`` o
    ``{"action": "ignore", "rule": name}`` (``rule`` es ``None`` si la regla no
    tiene nombre): la web la manda tal cual al endpoint de revisión.
    """
    for rule in rules:
        if _matches(rule, workout, tz):
            if "sport" in rule:
                return {"action": "classify", "sport": rule["sport"], "rule": rule.get("name")}
            return {"action": "ignore", "rule": rule.get("name")}
    return None


def _matches(rule: dict[str, Any], workout: Mapping[str, Any], tz: str) -> bool:
    start, end = workout["start_ts"], workout["end_ts"]
    timed = {"minutes", "start", "weekdays", "months"} & rule.keys()
    if timed and (start is None or end is None):
        return False  # sin horas no se puede cumplir una condición sobre ellas
    local = datetime.fromtimestamp(start, ZoneInfo(tz)) if timed else None

    if "minutes" in rule:
        low, high = rule["minutes"]
        if not low <= (end - start) / 60 <= high:
            return False
    if "start" in rule:
        low, high = rule["start"]
        minute = local.hour * 60 + local.minute
        # low > high: la franja cruza la medianoche (22:15 → 01:30).
        if not (low <= minute <= high if low <= high else minute >= low or minute <= high):
            return False
    if "weekdays" in rule and local.isoweekday() not in rule["weekdays"]:
        return False
    if "months" in rule and local.month not in rule["months"]:
        return False
    if "max_load" in rule and (workout["train_load"] or 0) > rule["max_load"]:
        return False
    if "codes" in rule and workout["sport_type"] not in rule["codes"]:
        return False
    return True
