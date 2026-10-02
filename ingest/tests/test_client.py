"""Tests de ``ingest.client`` sin red (mock de ``httpx.Client.request``).

Cubre: headers (``apptoken`` + ``appname: com.huami.midong`` en todos los
GET), retry único ante 401 con token fresco, error claro en códigos != 200,
paginación de ``sport_history``, y los params exactos de cada uno de los 8
endpoints validados (ver docs/zepp-api.md).
"""

from __future__ import annotations

import urllib.parse
from datetime import date

import httpx
import pytest

from ingest import client as client_mod

CONFIG = {"region_host": "api-mifit-de2.zepp.com", "tz": "Europe/Madrid"}


class FakeAuth:
    def __init__(self, app_token: str = "TOK", user_id: str = "777") -> None:
        self.app_token = app_token
        self.user_id_value = user_id
        self.get_calls = 0
        self.handle_401_calls = 0

    def get_app_token(self) -> tuple[str, str]:
        self.get_calls += 1
        return self.app_token, self.user_id_value

    def handle_401(self) -> tuple[str, str]:
        self.handle_401_calls += 1
        self.app_token = "FRESH"
        return self.app_token, self.user_id_value


def _query(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_get_sends_apptoken_and_appname_midong(fake_httpx):
    fake_httpx.queue(httpx.Response(200, json={"ok": True}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    result = c.weight(1000, 2000)

    assert result == {"ok": True}
    call = fake_httpx.calls[0]
    assert call.headers["apptoken"] == "TOK"
    assert call.headers["appname"] == "com.huami.midong"
    assert call.url.startswith("https://api-mifit-de2.zepp.com/users/777/members/-1/weightRecords")


def test_401_triggers_single_retry_with_fresh_token(fake_httpx):
    fake_httpx.queue(httpx.Response(401, json={}))
    fake_httpx.queue(httpx.Response(200, json={"ok": True}))
    auth_stub = FakeAuth()
    c = client_mod.ZeppClient(auth_stub, CONFIG)

    result = c.weight(1000, 2000)

    assert result == {"ok": True}
    assert auth_stub.handle_401_calls == 1
    assert len(fake_httpx.calls) == 2
    assert fake_httpx.calls[1].headers["apptoken"] == "FRESH"


def test_second_401_after_retry_raises_with_endpoint_and_status(fake_httpx):
    fake_httpx.queue(httpx.Response(401, json={}))
    fake_httpx.queue(httpx.Response(401, json={}))
    auth_stub = FakeAuth()
    c = client_mod.ZeppClient(auth_stub, CONFIG)

    with pytest.raises(client_mod.ZeppAPIError) as exc_info:
        c.weight(1000, 2000)

    assert auth_stub.handle_401_calls == 1
    assert len(fake_httpx.calls) == 2
    assert "weightRecords" in str(exc_info.value)
    assert "401" in str(exc_info.value)


def test_5xx_persistente_agota_los_reintentos_y_sube_el_error(fake_httpx, no_backoff):
    for _ in range(client_mod.MAX_ATTEMPTS):
        fake_httpx.queue(httpx.Response(500, text="boom"))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    with pytest.raises(client_mod.ZeppAPIError) as exc_info:
        c.band_data(date(2026, 7, 1), date(2026, 7, 1))

    assert len(fake_httpx.calls) == client_mod.MAX_ATTEMPTS
    assert "500" in str(exc_info.value)
    assert "band_data.json" in str(exc_info.value)


# Los 502/503 sueltos del backend de Zepp eran la causa real de los
# "Fuentes con error: 1" en el sync: se reintenta en vez de perder el día.
@pytest.mark.parametrize("status", sorted(client_mod.RETRY_STATUS))
def test_fallo_transitorio_se_reintenta_y_acaba_bien(fake_httpx, no_backoff, status):
    fake_httpx.queue(httpx.Response(status, text="upstream caído"))
    fake_httpx.queue(httpx.Response(200, json={"ok": True}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    assert c.band_data(date(2026, 7, 1), date(2026, 7, 1)) == {"ok": True}
    assert len(fake_httpx.calls) == 2


def test_corte_de_transporte_se_reintenta(fake_httpx, no_backoff):
    def boom(_record):
        raise httpx.ConnectTimeout("timeout")

    fake_httpx.queue(boom)
    fake_httpx.queue(httpx.Response(200, json={"ok": True}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    assert c.band_data(date(2026, 7, 1), date(2026, 7, 1)) == {"ok": True}
    assert len(fake_httpx.calls) == 2


def test_corte_de_transporte_persistente_sube_el_error_original(fake_httpx, no_backoff):
    def boom(_record):
        raise httpx.ConnectTimeout("timeout")

    for _ in range(client_mod.MAX_ATTEMPTS):
        fake_httpx.queue(boom)
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    with pytest.raises(httpx.ConnectTimeout):
        c.band_data(date(2026, 7, 1), date(2026, 7, 1))

    assert len(fake_httpx.calls) == client_mod.MAX_ATTEMPTS


def test_4xx_no_se_reintenta(fake_httpx, no_backoff):
    """Un 403 es config nuestra (host/región/appname), no congestión:
    reintentarlo solo retrasa el diagnóstico."""
    fake_httpx.queue(httpx.Response(403, text="forbidden"))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    with pytest.raises(client_mod.ZeppAPIError):
        c.band_data(date(2026, 7, 1), date(2026, 7, 1))

    assert len(fake_httpx.calls) == 1


def test_429_respeta_retry_after(fake_httpx, monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(client_mod.time, "sleep", delays.append)
    monkeypatch.setattr(client_mod.random, "random", lambda: 0.5)  # jitter neutro (x1.0)
    fake_httpx.queue(httpx.Response(429, text="slow down", headers={"retry-after": "2"}))
    fake_httpx.queue(httpx.Response(200, json={"ok": True}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    assert c.band_data(date(2026, 7, 1), date(2026, 7, 1)) == {"ok": True}
    assert delays == [2.0]


def test_el_backoff_crece_entre_intentos(fake_httpx, monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(client_mod.time, "sleep", delays.append)
    monkeypatch.setattr(client_mod.random, "random", lambda: 0.5)
    for _ in range(client_mod.MAX_ATTEMPTS):
        fake_httpx.queue(httpx.Response(502, text="bad gateway"))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    with pytest.raises(client_mod.ZeppAPIError):
        c.band_data(date(2026, 7, 1), date(2026, 7, 1))

    # una espera menos que intentos: tras el último no se espera para nada
    assert delays == [0.5, 1.0]


def test_sport_history_pagination_params_omitted_by_default(fake_httpx):
    fake_httpx.queue(httpx.Response(200, json={"data": {"summary": []}}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    c.sport_history()

    qs = _query(fake_httpx.calls[0].url)
    assert "startTrackId" not in qs
    assert "stopTrackId" not in qs
    assert qs["source"] == ["run.mifit.huami.com"]
    assert qs["userid"] == ["777"]


def test_sport_history_pagination_params_included_when_given(fake_httpx):
    fake_httpx.queue(httpx.Response(200, json={"data": {"summary": []}}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    c.sport_history(start_track_id=111, stop_track_id=222)

    qs = _query(fake_httpx.calls[0].url)
    assert qs["startTrackId"] == ["111"]
    assert qs["stopTrackId"] == ["222"]


ENDPOINT_CASES = [
    (
        "sport_load",
        lambda c: c.sport_load(date(2026, 6, 1), date(2026, 7, 1)),
        "/v2/watch/users/777/WatchSportStatistics/SPORT_LOAD",
        {"startDay": ["2026-06-01"], "endDay": ["2026-07-01"]},
    ),
    (
        "vo2max",
        lambda c: c.vo2max(date(2026, 6, 1), date(2026, 7, 1)),
        "/v2/watch/users/777/WatchSportStatistics/VO2_MAX",
        {"startDay": ["2026-06-01"], "endDay": ["2026-07-01"]},
    ),
    (
        "events",
        lambda c: c.events("Charge", "real_data", 1000, 2000),
        "/v2/users/me/events",
        {"eventType": ["Charge"], "subType": ["real_data"], "from": ["1000"], "to": ["2000"]},
    ),
    (
        "band_data",
        lambda c: c.band_data(date(2026, 7, 1), date(2026, 7, 1)),
        "/v1/data/band_data.json",
        {"userid": ["777"], "from_date": ["2026-07-01"], "to_date": ["2026-07-01"]},
    ),
    (
        "weight",
        lambda c: c.weight(1000, 2000),
        "/users/777/members/-1/weightRecords",
        {"fromTime": ["1000"], "toTime": ["2000"]},
    ),
    (
        "sport_detail",
        lambda c: c.sport_detail(1700000000, "run.1000001.huami.com"),
        "/v1/sport/run/detail.json",
        {"trackid": ["1700000000"], "source": ["run.1000001.huami.com"]},
    ),
    (
        "file_info_events",
        lambda c: c.file_info_events("SEC_HR", "detail", 1000, 2000),
        "/users/me/fileInfo/events",
        {"eventType": ["SEC_HR"], "subType": ["detail"], "from": ["1000"], "to": ["2000"]},
    ),
]


@pytest.mark.parametrize("name,call,expected_path,expected_params", ENDPOINT_CASES)
def test_endpoint_hits_expected_path_and_params(fake_httpx, name, call, expected_path, expected_params):
    fake_httpx.queue(httpx.Response(200, json={"data": {}}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    call(c)

    request = fake_httpx.calls[0]
    assert expected_path in request.url
    qs = _query(request.url)
    for key, expected_value in expected_params.items():
        assert qs[key] == expected_value


def test_all_get_requests_use_random_r_param_and_configured_timezone(fake_httpx):
    fake_httpx.queue(httpx.Response(200, json={"ok": True}))
    c = client_mod.ZeppClient(FakeAuth(), CONFIG)

    c.weight(1000, 2000)

    call = fake_httpx.calls[0]
    qs = _query(call.url)
    assert "r" in qs and qs["r"][0]
    assert call.headers["timezone"] == "Europe/Madrid"
