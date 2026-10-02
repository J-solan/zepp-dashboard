"""Carga de ``ingest/config.toml``, en un solo sitio.

Lo usan la CLI de login, la ingesta, el import de Hevy y el backend: sin esto
cada uno abría el TOML por su cuenta y el mensaje de "falta el fichero" era
distinto (o inexistente) en cada uno.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "ingest" / "config.toml"


def load_config(path: Path | str = CONFIG_PATH, *, required: bool = True) -> dict[str, Any]:
    """El config como dict. Con ``required=False`` devuelve ``{}`` si no existe
    (el backend arranca sin config: sirve lo que ya haya en la BBDD y solo
    falla el sync bajo demanda)."""
    path = Path(path)
    if not path.exists():
        if required:
            raise SystemExit(f"ERROR: no existe {path}. Copia ingest/config.example.toml y rellénalo.")
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)
