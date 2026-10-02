"""Autenticación Zepp: login como webapp (``com.huami.webapp``) → ``app_token``.

Login en 2 fases, validado en vivo y basado en el flujo de
``argrento/huami-token``:
  1. ``ZEPP_TOKENS``: credenciales cifradas (AES-128-CBC) → redirect 303 con
     ``access``/``refresh`` token en la query del ``Location``.
  2. ``ZEPP_LOGIN``: intercambia el ``access_token`` por el ``app_token``
     (header ``apptoken`` de todas las llamadas de datos). Se declara
     ``app_name=com.huami.webapp`` para no expulsar la sesión del móvil
     (que usa ``com.huami.midong``) — ver ``docs/zepp-api.md``.

Persiste el ``app_token`` en disco (chmod 600) y lo reutiliza mientras el
servidor lo acepte; ante un 401 el llamador debe invocar ``handle_401``.

**Refresh token**: la fase 1 devuelve también un ``refresh_token``, pero no
se ha encontrado ningún endpoint de renovación en las referencias consultadas
(``huami-token``: captura el token y no lo vuelve a usar en ningún sitio;
``zepp-health-cli``: ni siquiera implementa login, solo consume un
``app_token`` ya obtenido) → **no disponible**. Ante 401 se hace re-login completo directamente
(máx. 1 intento por ejecución, para respetar el rate-limit/429 del endpoint).

Se puede usar suelto, sin el resto del proyecto::

    uv run python -m ingest.auth          # imprime app_token y user_id
    uv run python -m ingest.auth --force  # ignora la caché y re-loguea
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ingest.config import load_config

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_CACHE_PATH = ROOT / "data" / "app_token.json"

# Host de login por defecto: validado en vivo, no varía con la región de
# datos (huami-token tampoco detecta país/región para esto:
# usa siempre region="us-west-2"/country_code="US" en el payload de fase 1,
# incluso para cuentas EU). ``login_host`` en config permite override manual;
# el host de fase 2 se deriva sustituyendo el prefijo "api-user-" por
# "api-mifit-" (mismo patrón que host de fase 1/fase 2 observado).
DEFAULT_TOKENS_HOST = "api-user-us2.zepp.com"

_AES_KEY = b"xeNtBVqzDc6tuNTh"
_AES_IV = b"MAAAYAAAAAAAAABg"

HEADERS_ZEPP_TOKENS = {
    "app_name": "com.huami.midong",
    "appname": "com.huami.midong",
    "cv": "151689_9.12.5",
    "v": "2.0",
    "appplatform": "android_phone",
    "vb": "202509151347",
    "vn": "9.12.5",
    "user-agent": "Zepp/9.12.5 (Pixel 4; Android 12; Density/2.75)",
    "x-hm-ekv": "1",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept-encoding": "gzip",
}

HEADERS_ZEPP_LOGIN = {
    "app_name": "com.huami.webapp",
    "origin": "https://user.zepp.com",
    "referer": "https://user.zepp.com/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.5",
}


class AuthError(RuntimeError):
    """Fallo de autenticación Zepp (fase de tokens, login, o 401 sin recuperación)."""


def _aes128_cbc_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _login_phase_host(tokens_host: str) -> str:
    return tokens_host.replace("api-user-", "api-mifit-", 1)


class ZeppAuth:
    def __init__(self, config: dict[str, Any], token_cache_path: Path | str | None = None) -> None:
        self.email: str = config["email"]
        self.password: str = config["password"]
        self.tokens_host: str = config.get("login_host", DEFAULT_TOKENS_HOST)
        self.login_host: str = _login_phase_host(self.tokens_host)
        self.token_cache_path = Path(token_cache_path or DEFAULT_TOKEN_CACHE_PATH)

        self._app_token: str | None = None
        self._user_id: str | None = None
        self._logged_in_this_run = False
        # El login registra sesión y tiene rate-limit agresivo (429), así que debe
        # ser ÚNICO aunque varios GET en paralelo resuelvan el token a la vez:
        # este lock lo serializa.
        self._lock = threading.Lock()

    def get_app_token(self) -> tuple[str, str]:
        """(app_token, user_id): en memoria > cache en disco > login."""
        if self._app_token is not None:
            return self._app_token, self._user_id  # type: ignore[return-value]

        with self._lock:
            if self._app_token is not None:  # otro hilo lo resolvió mientras esperaba
                return self._app_token, self._user_id  # type: ignore[return-value]
            cached = self._load_cache()
            if cached is not None:
                self._app_token, self._user_id = cached["app_token"], cached["user_id"]
            else:
                self._login()
            return self._app_token, self._user_id  # type: ignore[return-value]

    def handle_401(self) -> tuple[str, str]:
        """Re-login completo ante 401. Máximo 1 intento por ejecución."""
        with self._lock:
            if self._logged_in_this_run:
                raise AuthError("401 tras re-login: credenciales inválidas o cuenta bloqueada")
            self._login()
            return self._app_token, self._user_id  # type: ignore[return-value]

    def _login(self) -> None:
        access_token = self._fetch_access_token()
        self._exchange_for_app_token(access_token)
        self._save_cache()
        self._logged_in_this_run = True

    def _fetch_access_token(self) -> str:
        payload = {
            "emailOrPhone": self.email,
            "state": "REDIRECTION",
            "client_id": "HuaMi",
            "password": self.password,
            "redirect_uri": "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html",
            "region": "us-west-2",
            "token": ["access", "refresh"],
            "country_code": "US",
        }
        encoded = urllib.parse.urlencode(payload, doseq=True).encode()
        encrypted = _aes128_cbc_encrypt(encoded, _AES_KEY, _AES_IV)

        with httpx.Client(follow_redirects=False, timeout=30.0) as client:
            response = client.post(
                f"https://{self.tokens_host}/v2/registrations/tokens",
                content=encrypted,
                headers=HEADERS_ZEPP_TOKENS,
            )
        if response.status_code != 303:
            raise AuthError(
                f"ZEPP_TOKENS: se esperaba 303, llegó {response.status_code}: {response.text[:300]}"
            )
        location = response.headers.get("location")
        if not location:
            raise AuthError("ZEPP_TOKENS: sin header Location en la redirección")
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        access_token = qs.get("access", [None])[0]
        if not access_token:
            raise AuthError(f"ZEPP_TOKENS: no se encontró access_token en {location}")
        return access_token

    def _exchange_for_app_token(self, access_token: str) -> None:
        payload = {
            "code": access_token,
            "device_id": str(uuid.uuid4()),
            "device_model": "android_phone",
            "app_version": "9.12.5",
            "dn": (
                "api-mifit.zepp.com,api-user.zepp.com,api-mifit.zepp.com,"
                "api-watch.zepp.com,app-analytics.zepp.com,auth.zepp.com,"
                "api-analytics.zepp.com"
            ),
            "third_name": "huami",
            "source": "com.huami.watch.hmwatchmanager:9.12.5:151689",
            "app_name": "com.huami.webapp",
            "country_code": "US",
            "grant_type": "access_token",
            "allow_registration": "false",
            "lang": "en",
            "countryState": "US-NY",
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"https://{self.login_host}/v2/client/login",
                data=payload,
                headers=HEADERS_ZEPP_LOGIN,
            )
        if response.status_code != 200:
            raise AuthError(f"ZEPP_LOGIN: status {response.status_code}: {response.text[:300]}")
        token_info = response.json().get("token_info", {})
        app_token = token_info.get("app_token")
        user_id = token_info.get("user_id")
        if not app_token or not user_id:
            raise AuthError(f"ZEPP_LOGIN: respuesta sin app_token/user_id: {token_info}")
        self._app_token = app_token
        self._user_id = str(user_id)

    def _load_cache(self) -> dict[str, str] | None:
        if not self.token_cache_path.exists():
            return None
        return json.loads(self.token_cache_path.read_text())

    def _save_cache(self) -> None:
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_cache_path.write_text(
            json.dumps(
                {
                    "app_token": self._app_token,
                    "user_id": self._user_id,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )
        self.token_cache_path.chmod(0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ingest.auth",
        description="Loguea en Zepp y muestra el app_token (header 'apptoken') y el user_id.",
    )
    parser.add_argument(
        "--force", action="store_true", help="ignora el token cacheado y vuelve a loguear"
    )
    args = parser.parse_args(argv)

    auth = ZeppAuth(load_config())
    if args.force:
        auth.token_cache_path.unlink(missing_ok=True)

    try:
        app_token, user_id = auth.get_app_token()
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"app_token: {app_token}")
    print(f"user_id:   {user_id}")
    print(f"\nCacheado en {auth.token_cache_path} (chmod 600). Caduca a los ~30 días.")
    print("Las peticiones de datos van con los headers 'apptoken' y 'appname: com.huami.midong'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
