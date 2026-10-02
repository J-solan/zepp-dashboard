-- Título del workout de Hevy ("Entrenamiento 💪", "Pierna", ...).
--
-- Hasta ahora solo se hasheaba dentro de ``external_id`` y se perdía. La cola
-- de revisión lo necesita literal: al preguntar "¿qué hiciste aquí?" sobre un
-- 223 se muestra como evidencia el entreno de Hevy de ese mismo día ("ese día
-- registraste 'Entrenamiento 💪' en Hevy, 12 series"), y un hash no se lee.
--
-- Queda NULL en las filas ya importadas hasta el siguiente ``hevy import``
-- (el UPSERT lo rellena; el import es idempotente).
ALTER TABLE workout ADD COLUMN title TEXT;
