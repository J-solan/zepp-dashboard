"""Cliente HTTP: SOLO los endpoints validados.

Header ``apptoken`` para autenticar y ``appname: com.huami.midong`` en los GET
de datos (truco de namespace para ver el scope completo, ver ``docs/zepp-api.md``). Params validados en vivo, y tomados de ``zepp-health-cli`` para los
endpoints que no se pudieron comprobar directamente.

Devuelve dicts crudos: sin parsear, sin escribir en DB (eso es run.py).
"""

from __future__ import annotations

import random
import time
import uuid
from datetime import date
from typing import Any

import httpx

DATA_HEADERS_BASE = {
    "appname": "com.huami.midong",
    "appplatform": "ios_phone",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "v": "2.0",
    "vn": "10.2.5",
    "cv": "1722_10.2.5",
    "vb": "202604132257",
    "user-agent": "Zepp/10.2.5 (iPhone; iOS 26.3.1; Scale/3.00)",
    "lang": "en",
    "country": "",
}


# Reintentos ante fallo TRANSITORIO del servidor de Zepp. Una ventana de 30
# días son ~300 GET en paralelo y el backend devuelve 502/503 sueltos cada
# pocas ejecuciones; sin reintento, cada uno tumbaba esa (fuente, día) entera y
# el sync acababa con "error: N" sin causa real ni forma de saber cuál era.
# Solo se reintenta lo que puede arreglarse esperando: 5xx, 429 y cortes de
# transporte (timeout, conexión caída). Un 4xx es un error nuestro y sube tal
# cual, para no enmascararlo.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5
BACKOFF_MAX_S = 10.0


class ZeppAPIError(RuntimeError):
    def __init__(self, endpoint: str, status_code: int, body: str) -> None:
        super().__init__(f"{endpoint}: status {status_code}: {body}")
        self.endpoint = endpoint
        self.status_code = status_code


class ZeppClient:
    def __init__(self, auth: Any, config: dict[str, Any], timeout: float = 30.0) -> None:
        self.auth = auth
        self.host: str = config["region_host"]
        self.tz: str = config["tz"]
        self._client = httpx.Client(timeout=timeout)
        self._user_id: str | None = None

    @property
    def user_id(self) -> str:
        if self._user_id is None:
            _, self._user_id = self.auth.get_app_token()
        return self._user_id

    def _request(self, path: str, params: dict[str, Any], app_token: str) -> httpx.Response:
        headers = dict(DATA_HEADERS_BASE)
        headers["apptoken"] = app_token
        headers["timezone"] = self.tz
        query = {"r": str(uuid.uuid4()).upper(), **params}
        return self._client.get(f"https://{self.host}{path}", params=query, headers=headers)

    def _sleep_backoff(self, attempt: int, retry_after: str | None) -> None:
        """Espera exponencial con jitter. El jitter importa: los GET salen en
        paralelo, y sin él todos reintentarían en el mismo instante."""
        if retry_after and retry_after.strip().isdigit():
            delay = min(float(retry_after.strip()), BACKOFF_MAX_S)
        else:
            delay = min(BACKOFF_BASE_S * 2 ** (attempt - 1), BACKOFF_MAX_S)
        time.sleep(delay * (0.5 + random.random()))

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        app_token, _ = self.auth.get_app_token()
        refreshed = False
        last_error: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._request(path, params, app_token)
            except httpx.TransportError as exc:  # timeout, DNS, conexión caída
                last_error = exc
                if attempt < MAX_ATTEMPTS:
                    self._sleep_backoff(attempt, None)
                continue

            # El token caducado se renueva una sola vez y se reintenta ya, sin
            # esperar: no es congestión, es credencial.
            if response.status_code == 401 and not refreshed:
                refreshed = True
                app_token, _ = self.auth.handle_401()
                continue

            if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                last_error = ZeppAPIError(path, response.status_code, response.text[:300])
                self._sleep_backoff(attempt, response.headers.get("retry-after"))
                continue

            if response.status_code != 200:
                raise ZeppAPIError(path, response.status_code, response.text[:300])
            return response.json()

        raise last_error  # type: ignore[misc]  # inalcanzable con last_error None

    # ------------------------------------------------------------------
    # Endpoints validados (ver ``docs/zepp-api.md``)
    # ------------------------------------------------------------------

    def sport_load(self, start_day: date, end_day: date) -> Any:
        return self._get(
            f"/v2/watch/users/{self.user_id}/WatchSportStatistics/SPORT_LOAD",
            {"startDay": start_day.isoformat(), "endDay": end_day.isoformat(), "limit": 900, "isReverse": "true"},
        )

    def vo2max(self, start_day: date, end_day: date) -> Any:
        return self._get(
            f"/v2/watch/users/{self.user_id}/WatchSportStatistics/VO2_MAX",
            {"startDay": start_day.isoformat(), "endDay": end_day.isoformat(), "limit": 900, "isReverse": "true"},
        )

    def events(
        self, event_type: str, sub_type: str, from_ms: int, to_ms: int, *, limit: int = 500, reverse: bool = True
    ) -> Any:
        """``/v2/users/me/events`` — multiuso (BioCharge, readiness, hrv, stress...).

        Los presets (eventType/subType) documentados en ``docs/zepp-api.md`` los
        aplica el llamador; este método solo valida el endpoint genérico.
        """
        return self._get(
            "/v2/users/me/events",
            {
                "eventType": event_type,
                "subType": sub_type,
                "from": from_ms,
                "to": to_ms,
                "limit": limit,
                "reverse": 1 if reverse else 0,
            },
        )

    def events_user(
        self,
        event_type: str,
        from_ms: int,
        to_ms: int,
        *,
        sub_type: str | None = None,
        limit: int = 500,
        reverse: bool = True,
    ) -> Any:
        """``/users/{id}/events`` — timeline de usuario (all_day_stress, single_stress...).

        Scope DISTINTO de ``events`` (``/v2/users/me/events``): aquí viaja la
        serie de estrés que PINTA la app. El blob ``stressInfo`` de
        ``Charge/stress_data`` resultó ser un modelo/agregado denso (curva por
        minuto + coeficientes), no la serie dispersa que muestra la app.
        Params portados de ``zepp-health-cli`` (``events_user``).
        """
        params: dict[str, Any] = {
            "eventType": event_type,
            "from": from_ms,
            "to": to_ms,
            "limit": limit,
            "reverse": 1 if reverse else 0,
            "userId": self.user_id,
        }
        if sub_type:
            params["subType"] = sub_type
        return self._get(f"/users/{self.user_id}/events", params)

    def band_data(
        self, from_date: date, to_date: date, *, query_type: str = "detail", byte_length: int = 8, device_type: int = 0
    ) -> Any:
        return self._get(
            "/v1/data/band_data.json",
            {
                "userid": self.user_id,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "query_type": query_type,
                "byteLength": byte_length,
                "device_type": device_type,
            },
        )

    def weight(self, from_ts: int, to_ts: int, *, limit: int = 300) -> Any:
        return self._get(
            f"/users/{self.user_id}/members/-1/weightRecords",
            {"fromTime": from_ts, "toTime": to_ts, "limit": limit, "isForward": 0},
        )

    def sport_history(self, *, start_track_id: int | None = None, stop_track_id: int | None = None) -> Any:
        """Historial de workouts. ``source`` es literal fijo, NO filtro (ver docs/zepp-api.md, "Endpoints").

        Pagina con ``start_track_id``/``stop_track_id`` (unix ts) si la
        respuesta trae >200 workouts (campo ``data.next``).
        """
        params: dict[str, Any] = {"userid": self.user_id, "source": "run.mifit.huami.com"}
        if start_track_id is not None:
            params["startTrackId"] = start_track_id
        if stop_track_id is not None:
            params["stopTrackId"] = stop_track_id
        return self._get("/v1/sport/run/history.json", params)

    def sport_detail(self, trackid: int, source: str) -> Any:
        return self._get("/v1/sport/run/detail.json", {"trackid": trackid, "source": source})

    def file_info_events(self, event_type: str, sub_type: str, from_ms: int, to_ms: int, *, limit: int = 200) -> Any:
        return self._get(
            "/users/me/fileInfo/events",
            {"eventType": event_type, "subType": sub_type, "from": from_ms, "to": to_ms, "limit": limit},
        )
