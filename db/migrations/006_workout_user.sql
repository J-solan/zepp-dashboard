-- Capa de usuario sobre workout: lo que escribe la persona, no la ingesta.
--
-- El problema que resuelve: ``ingest/run.py::_upsert_workouts`` hace
-- ``DO UPDATE SET sport=..., start_ts=..., avg_hr=...`` en CADA sync, así que
-- cualquier edición sobre esas columnas se perdería en la siguiente
-- sincronización. Sin error y sin aviso.
--
-- La regla (ya establecida por ``user_sport``/``review_status`` y por la tabla
-- ``annotation``): lo que escribe el usuario vive donde la ingesta NO escribe.
-- Estas dos columnas quedan fuera del ``DO UPDATE SET`` a propósito.
--
-- Se llaman ``user_*`` en paralelo a ``sport``/``user_sport``: la columna sin
-- prefijo es lo que dice la fuente, la ``user_`` es lo que dices tú, y tú
-- ganas. Los endpoints devuelven el efectivo ya resuelto.
ALTER TABLE workout ADD COLUMN user_title TEXT;
ALTER TABLE workout ADD COLUMN notes TEXT;
