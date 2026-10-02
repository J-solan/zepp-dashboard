-- Import de Hevy (fuente de verdad de fuerza).
--
-- Numerada 004 y no 003: el prefijo numérico es la clave de
-- ``schema_migrations`` y el 003 ya lo ocupa ``003_annotation.sql`` (aplicado).
-- Un segundo fichero 003 se daría por aplicado y no correría nunca.

-- Mapa ejercicio -> músculos con intensidad, sembrado desde
-- ``ingest/muscle_map.toml`` en cada import (UPSERT).
--
-- Es una tabla de N músculos por ejercicio, no una columna: un press inclinado
-- es pecho, pero también hombro y tríceps, y el volumen semanal por músculo
-- (pestaña Entrenos, `/api/muscles/volume`) sale mal si cada serie cuenta solo para uno.
-- ``intensity`` 0-1 pondera esa contribución; 1.0 = músculo principal.
CREATE TABLE IF NOT EXISTS exercise_muscle (
  exercise  TEXT NOT NULL,
  muscle    TEXT NOT NULL,
  intensity REAL NOT NULL,
  PRIMARY KEY (exercise, muscle),
  CHECK (intensity > 0 AND intensity <= 1)
);

-- Vínculo hevy -> zepp: el workout de Hevy (ejercicio/reps/peso) apunta al
-- workout type-52 del strap (FC/carga/zonas/TE) del MISMO día local.
ALTER TABLE workout ADD COLUMN linked_workout_id INTEGER REFERENCES workout(id);

-- Las horas del export CSV de Hevy las teclea el usuario y no son fiables; el
-- tipo de serie sí viene del propio registro. Se guarda verbatim ('normal',
-- 'warmup', 'dropset', 'failure') para poder excluir el calentamiento de los
-- agregados de volumen sin perder la serie.
ALTER TABLE workout_set ADD COLUMN set_type TEXT;

CREATE INDEX IF NOT EXISTS idx_workout_set_workout ON workout_set(workout_id);
