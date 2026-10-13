-- Noches "fantasma": algunos ``band_data`` traen un ``slp`` hueco (st == ed,
-- sin fases, score 0, rhr 0). Se guardaba como una noche de 0 minutos y su
-- ``rhr`` acababa en ``daily_metrics.resting_hr = 0`` los días sin readiness.
-- El parser ya no las da (``ingest/parsers.py::parse_sleep`` devuelve None con
-- ``ed <= st``); esto limpia lo guardado antes con ese mismo criterio.
--
-- Fases primero: ``sleep_stage`` no tiene ON DELETE CASCADE.
DELETE FROM sleep_stage WHERE session_id IN (
  SELECT id FROM sleep_session WHERE is_nap = 0 AND end_ts <= start_ts);

DELETE FROM sleep_session WHERE is_nap = 0 AND end_ts <= start_ts;

-- 0 lpm es el centinela de "sin dato", no una frecuencia.
UPDATE daily_metrics SET resting_hr = NULL WHERE resting_hr = 0;
UPDATE sleep_session SET resting_hr = NULL WHERE resting_hr = 0;
