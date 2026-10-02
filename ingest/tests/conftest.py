"""Fixtures compartidas: mock de ``httpx.Client.request`` sin red.

Usado por ``test_auth.py`` y ``test_client.py`` para programar respuestas
canned y grabar las peticiones salientes (método, url, headers, kwargs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx
import pytest


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: dict[str, str]
    kwargs: dict[str, Any]


class FakeHTTPX:
    def __init__(self) -> None:
        self.calls: list[RecordedRequest] = []
        self._responses: list[httpx.Response | Callable[[RecordedRequest], httpx.Response]] = []

    def queue(self, response: httpx.Response | Callable[[RecordedRequest], httpx.Response]) -> None:
        self._responses.append(response)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        full_url = httpx.URL(url, params=kwargs.get("params"))
        record = RecordedRequest(
            method=method, url=str(full_url), headers=dict(kwargs.get("headers") or {}), kwargs=kwargs
        )
        self.calls.append(record)
        if not self._responses:
            raise AssertionError(f"sin respuesta programada para {method} {url}")
        response = self._responses.pop(0)
        return response(record) if callable(response) else response


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> FakeHTTPX:
    fake = FakeHTTPX()
    monkeypatch.setattr(httpx.Client, "request", fake.request)
    return fake


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anula la espera entre reintentos del cliente: los tests comprueban
    CUÁNTAS veces se reintenta, no cuánto se duerme (eso tiene su propio test)."""
    from ingest import client as client_mod

    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)
