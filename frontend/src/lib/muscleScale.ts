/** Escala de color del body-map: volumen del músculo -> cuánto acento lleva.
 *
 * Normalización LINEAL contra el MÁXIMO del rango, no contra un absoluto: la
 * pregunta que contesta el mapa es "qué he trabajado más esta semana", y un
 * tope fijo dejaría semanas enteras casi neutras (o saturadas) según la carga.
 */

/** Suelo de tinte para un músculo con volumen > 0: sin él, un músculo con poco
 * volumen se ve idéntico a uno que no se tocó, y eso es justo lo contrario de
 * lo que hay que leer. El 0 sigue siendo 0 (neutro puro). Basta con poco
 * porque el cuerpo es casi papel: la primera serie ya se ve. */
const FLOOR_PCT = 12

/** % de acento (0-100) del músculo. `max` es el volumen del músculo más
 * trabajado del rango; con `max` 0 (rango sin fuerza) todo queda neutro. */
export function accentPct(volume: number, max: number): number {
  if (!(max > 0) || volume <= 0) return 0
  return Math.round(FLOOR_PCT + (100 - FLOOR_PCT) * Math.min(volume / max, 1))
}

/** Cuerpo sin carga: papel apenas ensuciado. Lo que dibuja el músculo cuando
 * no tiene volumen es su contorno, no el relleno. */
export const BODY_FILL = 'color-mix(in oklab, var(--color-page) 94%, var(--color-ink))'

/** Relleno OPACO del músculo: acento mezclado sobre el cuerpo, como una lámina
 * de anatomía coloreada. */
export function muscleFill(volume: number, max: number): string {
  const pct = accentPct(volume, max)
  if (pct === 0) return BODY_FILL
  return `color-mix(in oklab, var(--color-accent) ${pct}%, ${BODY_FILL})`
}
