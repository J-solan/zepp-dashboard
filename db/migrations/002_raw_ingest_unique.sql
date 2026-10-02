-- raw_ingest guarda el ÚLTIMO crudo por (source, day): lo que ya hacía el
-- código (ingest/run.py::store_raw) pasa aquí a ser invariante de esquema.
--
-- Dedupe previo OBLIGATORIO: una DB anterior a este índice puede tener varias filas
-- por (source, day) y el índice único fallaría. Se conserva la de id más alto
-- (la más reciente). NOTA: GROUP BY trata los NULL como iguales, así que las
-- filas con day NULL también se colapsan a una.
DELETE FROM raw_ingest
WHERE id NOT IN (SELECT MAX(id) FROM raw_ingest GROUP BY source, day);

CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_ingest_source_day
  ON raw_ingest(source, day);
