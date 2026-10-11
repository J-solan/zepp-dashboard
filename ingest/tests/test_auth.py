"""Tests de ``ingest.auth`` sin red (mock de ``httpx.Client.request``).

Cubre: login 2 fases (headers correctos por fase), reuso de token cacheado,
persistencia con permisos 600, y el flujo de recuperación ante 401 (máx. 1
re-login por ejecución, sin bucle).
"""

from __future__ import annotations

import json
import stat
import threading
import time

import httpx
import pytest

from ingest import auth

CONFIG = {"email": "user@example.com", "password": "secret"}


def _redirect_response(access: str = "ACCESS1", refresh: str = "REFRESH1") -> httpx.Response:
    location = (
        "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"
        f"?access={access}&refresh={refresh}"
    )
    return httpx.Response(303, headers={"location": location})


def _login_response(app_token: str = "TOKEN1", user_id: str = "12345") -> httpx.Response:
    return httpx.Response(
        200,
        json={"token_info": {"app_token": app_token, "user_id": user_id, "login_token": "L1"}},
    )


def test_login_phase_headers_are_midong_and_webapp_respectively(fake_httpx, tmp_path):
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(_login_response())

    a = auth.ZeppAuth(CONFIG, token_cache_path=tmp_path / "app_token.json")
    app_token, user_id = a.get_app_token()

    assert app_token == "TOKEN1"
    assert user_id == "12345"
    assert len(fake_httpx.calls) == 2
    tokens_call, login_call = fake_httpx.calls
    assert tokens_call.headers["appname"] == "com.huami.midong"
    assert tokens_call.headers["app_name"] == "com.huami.midong"
    assert login_call.headers["app_name"] == "com.huami.webapp"


def test_login_default_hosts_match_validated_script(fake_httpx, tmp_path):
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(_login_response())

    a = auth.ZeppAuth(CONFIG, token_cache_path=tmp_path / "app_token.json")
    a.get_app_token()

    tokens_call, login_call = fake_httpx.calls
    assert tokens_call.url.startswith("https://api-user-us2.zepp.com/")
    assert login_call.url.startswith("https://api-mifit-us2.zepp.com/")


def test_login_host_override_from_config(fake_httpx, tmp_path):
    cfg = {**CONFIG, "login_host": "api-user-de2.zepp.com"}
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(_login_response())

    a = auth.ZeppAuth(cfg, token_cache_path=tmp_path / "app_token.json")
    a.get_app_token()

    tokens_call, login_call = fake_httpx.calls
    assert tokens_call.url.startswith("https://api-user-de2.zepp.com/")
    assert login_call.url.startswith("https://api-mifit-de2.zepp.com/")


def test_token_persisted_with_chmod_600(fake_httpx, tmp_path):
    cache_path = tmp_path / "app_token.json"
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(_login_response())

    a = auth.ZeppAuth(CONFIG, token_cache_path=cache_path)
    a.get_app_token()

    assert cache_path.exists()
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600
    saved = json.loads(cache_path.read_text())
    assert saved["app_token"] == "TOKEN1"
    assert saved["user_id"] == "12345"


def test_cached_token_reused_without_network_call(fake_httpx, tmp_path):
    cache_path = tmp_path / "app_token.json"
    cache_path.write_text(
        json.dumps({"app_token": "CACHED", "user_id": "999", "cached_at": "2026-01-01T00:00:00+00:00"})
    )

    a = auth.ZeppAuth(CONFIG, token_cache_path=cache_path)
    app_token, user_id = a.get_app_token()

    assert (app_token, user_id) == ("CACHED", "999")
    assert fake_httpx.calls == []


def test_get_app_token_is_memoized_in_process(fake_httpx, tmp_path):
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(_login_response())

    a = auth.ZeppAuth(CONFIG, token_cache_path=tmp_path / "app_token.json")
    a.get_app_token()
    a.get_app_token()

    assert len(fake_httpx.calls) == 2  # segunda llamada no repite login ni relee el fichero


def test_handle_401_relogs_in_once_and_returns_fresh_token(fake_httpx, tmp_path):
    cache_path = tmp_path / "app_token.json"
    cache_path.write_text(json.dumps({"app_token": "STALE", "user_id": "999", "cached_at": "x"}))
    fake_httpx.queue(_redirect_response(access="ACCESS2", refresh="REFRESH2"))
    fake_httpx.queue(_login_response(app_token="FRESH", user_id="999"))

    a = auth.ZeppAuth(CONFIG, token_cache_path=cache_path)
    a.get_app_token()
    assert fake_httpx.calls == []  # cargado de cache, aún sin red

    app_token, user_id = a.handle_401("STALE")

    assert (app_token, user_id) == ("FRESH", "999")
    assert len(fake_httpx.calls) == 2


def _auth_with_stale_cache(fake_httpx, tmp_path) -> auth.ZeppAuth:
    cache_path = tmp_path / "app_token.json"
    cache_path.write_text(json.dumps({"app_token": "STALE", "user_id": "999", "cached_at": "x"}))
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(_login_response(app_token="FRESH", user_id="999"))
    a = auth.ZeppAuth(CONFIG, token_cache_path=cache_path)
    a.get_app_token()
    return a


def test_handle_401_with_already_renewed_token_returns_new_one_without_login(fake_httpx, tmp_path):
    """Varios GET en paralelo reciben 401 con el mismo token caducado: solo
    el primero re-loguea; el resto recibe el token nuevo, sin AuthError."""
    a = _auth_with_stale_cache(fake_httpx, tmp_path)

    assert a.handle_401("STALE") == ("FRESH", "999")
    assert a.handle_401("STALE") == ("FRESH", "999")
    assert len(fake_httpx.calls) == 2  # un único login


def test_handle_401_with_renewed_token_raises_without_looping(fake_httpx, tmp_path):
    """Un 401 con el token recién obtenido ya no es caducidad: se mantiene
    el tope de 1 re-login por ejecución."""
    a = _auth_with_stale_cache(fake_httpx, tmp_path)
    a.handle_401("STALE")
    assert len(fake_httpx.calls) == 2

    with pytest.raises(auth.AuthError):
        a.handle_401("FRESH")
    assert len(fake_httpx.calls) == 2  # no dispara una tercera petición (respeta el 429)


def test_login_is_serialized_under_concurrency(tmp_path):
    """Varios GET en paralelo resolviendo el token a la vez deben
    disparar UN SOLO login (el endpoint tiene rate-limit 429)."""
    logins = []

    class SlowAuth(auth.ZeppAuth):
        def _login(self) -> None:
            logins.append(1)
            time.sleep(0.05)  # ventana amplia para que otros hilos entren
            self._app_token = "TOK"
            self._user_id = "UID"
            self._logged_in_this_run = True

    a = SlowAuth(CONFIG, token_cache_path=tmp_path / "app_token.json")  # sin cache -> login
    results: list[tuple[str, str]] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()  # los 8 hilos entran a get_app_token simultáneamente
        results.append(a.get_app_token())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(logins) == 1
    assert set(results) == {("TOK", "UID")}


def test_failed_relogin_is_not_retried_by_waiting_workers(fake_httpx, tmp_path):
    """Si el re-login falla (p. ej. 429), los workers que esperaban el lock no
    lo reintentan: martillear el login solo alarga el bloqueo."""
    cache_path = tmp_path / "app_token.json"
    cache_path.write_text(json.dumps({"app_token": "STALE", "user_id": "999", "cached_at": "x"}))
    fake_httpx.queue(httpx.Response(429, text="rate limited"))
    a = auth.ZeppAuth(CONFIG, token_cache_path=cache_path)
    a.get_app_token()

    with pytest.raises(auth.AuthError):
        a.handle_401("STALE")
    with pytest.raises(auth.AuthError):
        a.handle_401("STALE")
    assert len(fake_httpx.calls) == 1


def test_tokens_phase_non_303_raises_auth_error(fake_httpx, tmp_path):
    fake_httpx.queue(httpx.Response(429, text="rate limited"))

    a = auth.ZeppAuth(CONFIG, token_cache_path=tmp_path / "app_token.json")
    with pytest.raises(auth.AuthError):
        a.get_app_token()


def test_login_phase_non_200_raises_auth_error(fake_httpx, tmp_path):
    fake_httpx.queue(_redirect_response())
    fake_httpx.queue(httpx.Response(500, text="boom"))

    a = auth.ZeppAuth(CONFIG, token_cache_path=tmp_path / "app_token.json")
    with pytest.raises(auth.AuthError):
        a.get_app_token()
