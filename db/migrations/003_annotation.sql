-- Anotaciones manuales del usuario sobre la línea de tiempo: un tramo
-- [start_ts, end_ts] con un texto ("reunión tensa", "café doble", "resaca").
--
-- Es la ÚNICA tabla escrita por el usuario y no por la ingesta: ninguna
-- fuente de Zepp la toca, así que un re-sync o un backfill jamás la pisan.
--
-- Deliberadamente NO tiene columna de métrica: una anotación describe un
-- hecho del día, no una gráfica. El mismo "café a las 17:00" explica a la vez
-- el pico de FC y el de estrés, y así la IA recibe un único diario en vez de
-- la misma nota duplicada por serie.
CREATE TABLE IF NOT EXISTS annotation (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  start_ts   INTEGER NOT NULL,
  end_ts     INTEGER NOT NULL,
  text       TEXT    NOT NULL,
  created_at INTEGER NOT NULL,
  CHECK (end_ts >= start_ts),
  CHECK (length(trim(text)) > 0)
);

-- Las consultas siempre son "las que solapan con [from, to]", que con el
-- filtro por end_ts arranca en este índice.
CREATE INDEX IF NOT EXISTS idx_annotation_span ON annotation(end_ts, start_ts);
