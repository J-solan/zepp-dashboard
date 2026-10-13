"""La demo dentro del navegador: el backend de verdad sobre Pyodide (WebAssembly).

No hay servidor. Un Web Worker carga Pyodide, importa este módulo, llama a
``boot()`` una vez y pasa cada petición de la web por ``handle()``, que se la
da a la app ASGI directamente: mismas rutas, mismas consultas y misma BBDD de
demo que ``python -m demo``, solo que en memoria y en la pestaña del visitante.

Solo lo importan ese Worker (el build está en ``demo/web/``) y sus tests: la
API normal y ``python -m demo`` no pasan por aquí.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import traceback
import types
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from demo import SYNC_OFF_REASON

_app = None


def _run_without_threads() -> None:
    """WebAssembly no tiene hilos, y FastAPI manda los endpoints ``def`` (y la
    dependencia ``get_conn``) al threadpool de anyio. Todo ese camino acaba en
    ``anyio.to_thread.run_sync``: aquí corre la función en el sitio. En la
    pestaña solo hay un visitante, así que no se pierde concurrencia real."""
    import anyio.to_thread

    async def run_sync(func, *args, **_options):
        return func(*args)

    anyio.to_thread.run_sync = run_sync


def _stub_zepp_clients() -> None:
    """``ingest.auth`` e ``ingest.client`` importan ``httpx`` y ``cryptography``
    para hablar con Zepp, cosa que la demo nunca hace (el sync responde 503).
    En el navegador no se cargan: ~2,4 MB de descarga y ~0,4 s de arranque para
    nada. Si faltan, estos módulos vacíos dejan que el import funcione; si algo
    llegara a usarlos, fallaría con un error, no en silencio."""
    if importlib.util.find_spec("httpx") is None:
        sys.modules["httpx"] = types.ModuleType("httpx")
    if importlib.util.find_spec("cryptography") is None:
        for name in ("cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
                     "cryptography.hazmat.primitives.padding", "cryptography.hazmat.primitives.ciphers"):
            sys.modules[name] = types.ModuleType(name)
        ciphers = sys.modules["cryptography.hazmat.primitives.ciphers"]
        ciphers.Cipher = ciphers.algorithms = ciphers.modes = None


async def boot(db_path: str = "/tmp/demo.db", *, now: int | None = None) -> None:
    """Siembra la demo terminando hoy en ``db_path`` (que no debe existir) y crea la app."""
    global _app
    if sys.platform == "emscripten":
        _run_without_threads()
    _stub_zepp_clients()
    # Después de los parches: estos imports arrastran ``ingest.auth``.
    from backend.api import create_app
    from demo import seed

    now = int(time.time()) if now is None else now
    today = datetime.fromtimestamp(now, ZoneInfo(seed.DEFAULT_TZ)).date()
    seed.build(Path(db_path), today, until=now)
    _app = create_app(db_path=db_path, tz=seed.DEFAULT_TZ, sync_config=None, sync_off_reason=SYNC_OFF_REASON)


async def handle(method: str, url: str, body: str | None = None) -> dict:
    """Una petición HTTP a la app. ``url`` es ruta + query (``/api/daily?from=…``)."""
    raw_path, _, query = url.partition("?")
    headers = [(b"host", b"demo")]
    if body is not None:
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        # Como un servidor de verdad: ``path`` decodificado, ``raw_path`` tal cual.
        "path": unquote(raw_path),
        "raw_path": raw_path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 0),
        "server": ("demo", 80),
    }
    pending = [{"type": "http.request", "body": (body or "").encode(), "more_body": False}]
    response = {"status": 500, "headers": [], "body": b""}

    async def receive():
        return pending.pop() if pending else {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            response["status"] = message["status"]
            response["headers"] = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response["body"] += message.get("body", b"")

    try:
        await _app(scope, receive, send)
    except Exception:
        # Como uvicorn: Starlette ya ha respondido el 500 y relanza solo para
        # que el servidor lo registre. Aquí el registro es la consola.
        traceback.print_exc()
    content_type = next((v.decode() for k, v in response["headers"] if k.lower() == b"content-type"), "")
    return {"status": response["status"], "content_type": content_type, "body": response["body"].decode()}
