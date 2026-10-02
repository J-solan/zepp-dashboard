-- Etiquetas de deporte: color propio y existencia independiente del uso.
--
-- Hasta ahora una categoría solo existía si algún entreno la tenía escrita en
-- ``user_sport`` (``GET /api/sports`` la deducía de los datos). Eso bastaba
-- para "escribirla una vez es crearla", pero deja fuera dos cosas que el
-- usuario sí quiere: crear una etiqueta ANTES de usarla, y elegirle el color.
--
-- Color por DEPORTE y no por entreno a propósito: el color es un CÓDIGO que
-- comparten badge, filtro y gráficas (mismo color = mismo tipo). Por entreno,
-- dos sesiones de fuerza podrían salir de colores distintos y el código
-- dejaría de leerse de un vistazo.
--
-- ``color`` admite NULL: crear la etiqueta y elegirle color son dos gestos
-- distintos, y sin color el front sigue usando su hash determinista, que ya da
-- un color estable y distinto a cada nombre.
--
-- Esta tabla NO es la lista cerrada de categorías: ``user_sport`` sigue siendo
-- TEXT libre y ``/api/sports`` une ambas fuentes. Borrar una fila de aquí
-- quita el color y la etiqueta vacía, nunca toca los entrenos.
CREATE TABLE IF NOT EXISTS sport_style (
  sport TEXT PRIMARY KEY,
  color TEXT,
  CHECK (length(trim(sport)) > 0)
);
