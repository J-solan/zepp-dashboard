/** Colores de la app, referenciados como custom properties de `index.css`
 * (fuente única de verdad de los hex). Recharts pasa strings `stroke`/`fill`
 * tal cual al SVG, así que `var(--color-x)` se resuelve en el navegador. */

export const METRIC = {
  hr: 'var(--color-metric-hr)',
  stress: 'var(--color-metric-stress)',
  sleep: 'var(--color-metric-sleep)',
  bio: 'var(--color-metric-bio)',
  steps: 'var(--color-metric-steps)',
  readiness: 'var(--color-metric-readiness)',
  /** Carga de entreno. Antes tomaba prestado el color de otra métrica; tiene
   * el suyo desde que se pinta en su propio carril, al lado de las demás. */
  load: 'var(--color-load)',
} as const

export const BIO = {
  total: METRIC.bio,
  mental: 'var(--color-bio-mental)',
  physical: 'var(--color-bio-physical)',
} as const

export const ZONE = {
  relaxed: 'var(--color-zone-relaxed)',
  normal: 'var(--color-zone-normal)',
  medium: 'var(--color-zone-medium)',
  high: 'var(--color-zone-high)',
} as const

// Tipos de entreno. Reusan tokens ya existentes en vez de añadir colores
// nuevos: la paleta de la app ya tiene suficientes ejes y un badge no necesita
// identidad propia, solo distinguirse del de al lado. Ninguno cae cerca del
// acento (#b4471f): el acento es del dato y de las acciones, no del deporte —
// con `fuerza` en bio-physical todos los badges parecían el mismo naranja.
export const SPORT = {
  fuerza: 'var(--color-metric-sleep)', // violeta
  // Rosa y no azul: el azul es el color con el que el calendario de Temporada
  // pinta el readiness, y una marca de deporte encima de esa rampa se leía
  // como "un día muy bueno" en vez de como "aquí hubo vóley".
  voley_playa: 'var(--color-stage-rem)',
  // "Actividad detectada" y "Otro" NO son un deporte: gris a propósito, pero
  // ink-secondary y no ink-muted para que la pastilla de filtro (texto oscuro
  // sobre el color) tenga contraste suficiente.
  auto_ia: 'var(--color-ink-secondary)',
  otro: 'var(--color-ink-secondary)',
} as const

/** Rampa para los tipos escritos a mano ("pádel", "Bicicleta de vuelta
 * trabajo"…): `user_sport` es texto libre, así que el color se deriva del
 * propio texto. Hues bien separados entre sí, del acento y de los fijos de
 * `SPORT` (violeta y rosa). */
export const SPORT_RAMP = [
  'var(--color-metric-bio)', // verde
  'var(--color-metric-steps)', // oliva
  'var(--color-metric-readiness)', // azul
  'var(--color-load)', // ámbar
  'var(--color-stage-deep)', // azul marino
] as const

// Rampa de zonas de FC: gris → azul → verde → ámbar → naranja → rojo.
//
// Seis paradas y no cuatro porque el strap manda SEIS zonas: con una rampa
// corta, dos zonas seguidas caían en el mismo azul y la barra no se podía
// leer. Con una parada por zona cada tramo tiene su tono, y el orden es el
// clásico de cualquier pulsómetro (suave → duro), que ya se entiende sin
// leyenda. El acento de la app queda fuera a propósito.
export const ZONE_RAMP = [
  'var(--color-hr-idle)',
  'var(--color-zone-normal)',
  'var(--color-zone-relaxed)',
  'var(--color-zone-medium)',
  'var(--color-hr-hard)',
  'var(--color-zone-high)',
] as const

export const CHART = {
  grid: 'var(--color-grid)',
  axis: 'var(--color-ink-muted)',
  surface: 'var(--color-surface)',
  // Las anotaciones son del usuario, no del reloj: van en el acento de la app
  // para que no se confundan con ninguna serie ni con las zonas de estrés.
  annotation: 'var(--color-accent)',
} as const

/** Cinco pasos de la MISMA tinta, del papel al color pleno.
 *
 * Una rampa por mezcla y no cinco hex por métrica: el calendario colorea por
 * readiness, sueño, carga, HRV o pasos, y cada una necesita su escala. */
const RAMP_STEPS = [14, 32, 52, 74, 100]

export function rampStep(color: string, bucket: number): string {
  return `color-mix(in oklab, ${color} ${RAMP_STEPS[bucket] ?? 100}%, var(--color-page))`
}
