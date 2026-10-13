"""Demo de zepp-dashboard con datos inventados: ``uv run python -m demo``."""

# Aquí y no en ``__main__`` porque también lo usa ``demo.browser``, que no puede
# importar ``__main__`` (arrastra uvicorn, que en el navegador no existe).
SYNC_OFF_REASON = "modo demo: sincronización desactivada"
