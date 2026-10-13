-- Dos datos que ya llegaban en crudo y no se guardaban.
--
-- ``skin_temp_delta``: desviación de la temperatura de la piel de esa noche
-- respecto a tu línea base, en °C (``readiness.skinTempCalibrated`` / 100; ver
-- ``ingest/parsers.py::parse_readiness``).
--
-- ``load_7d*``: la carga acumulada de 7 días de SPORT_LOAD (``wtlSum``) y los
-- rangos que Zepp da para ESE acumulado. Van aparte de ``train_load`` (la carga
-- del día) porque son otra métrica: el rango óptimo no aplica a un día suelto.
-- Los rangos cambian cada pocos días, así que se guardan por día y no como
-- una constante.
ALTER TABLE daily_metrics ADD COLUMN skin_temp_delta REAL;
ALTER TABLE daily_metrics ADD COLUMN load_7d INTEGER;
ALTER TABLE daily_metrics ADD COLUMN load_7d_optimal_min INTEGER;
ALTER TABLE daily_metrics ADD COLUMN load_7d_optimal_max INTEGER;
ALTER TABLE daily_metrics ADD COLUMN load_7d_overreaching INTEGER;
