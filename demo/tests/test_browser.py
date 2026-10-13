"""La demo del navegador (``demo.browser``): la misma API, llamada sin servidor.

Aquí corre en CPython; ``demo/web/smoke.mjs`` la prueba dentro de Pyodide.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pytest

from demo import SYNC_OFF_REASON, browser, seed

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=ZoneInfo(seed.DEFAULT_TZ))
TODAY = NOW.date().isoformat()
WEEK_AGO = (NOW.date() - timedelta(days=6)).isoformat()


@pytest.fixture(scope="module", autouse=True)
def booted(tmp_path_factory):
    asyncio.run(browser.boot(str(tmp_path_factory.mktemp("browser") / "demo.db"), now=int(NOW.timestamp())))


def call(method: str, url: str, body: dict | None = None) -> dict:
    return asyncio.run(browser.handle(method, url, None if body is None else json.dumps(body)))


def ok_json(url: str):
    res = call("GET", url)
    assert res["status"] == 200, f"{url}: {res}"
    assert res["content_type"] == "application/json"
    return json.loads(res["body"])


def test_reads_answer_with_the_demo_ending_today():
    assert ok_json(f"/api/overview?date={TODAY}")["sleep"]
    assert len(ok_json(f"/api/daily?from={WEEK_AGO}&to={TODAY}")) == 7
    assert ok_json(f"/api/workouts?from={WEEK_AGO}&to={TODAY}") is not None
    assert ok_json("/api/workouts/pending")


def test_a_write_changes_the_queue():
    pending = ok_json("/api/workouts/pending")
    res = call("POST", f"/api/workouts/{pending[0]['id']}/review", {"action": "ignore"})
    assert res["status"] == 200, res
    assert len(ok_json("/api/workouts/pending")) == len(pending) - 1


def test_path_is_decoded_like_a_real_server():
    # La web manda el nombre con encodeURIComponent.
    res = call("PUT", f"/api/sports/{quote('vóley playa')}", {"color": "#123456"})
    assert res["status"] == 200, res
    assert {"name": "vóley playa", "color": "#123456"} in ok_json("/api/sports")


def test_sync_is_off():
    res = call("POST", "/api/sync")
    assert res["status"] == 503
    assert json.loads(res["body"])["detail"] == SYNC_OFF_REASON


def test_a_crash_is_a_500_not_an_exception(monkeypatch):
    # Como detrás de uvicorn: la web recibe un 500, no una promesa rechazada.
    import backend.api

    def boom(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(backend.api, "_day_range_ts", boom)
    assert call("GET", f"/api/hr?from={TODAY}&to={TODAY}")["status"] == 500
