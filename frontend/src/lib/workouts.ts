import { dayOfTs } from './date'
import { SPORT, SPORT_RAMP, ZONE_RAMP } from './palette'
import type { HrZone, Workout, WorkoutExercise } from './types'

const SPORT_LABELS: Record<string, string> = {
  fuerza: 'Fuerza',
  voley_playa: 'Vóley playa',
  auto_ia: 'Actividad detectada',
  otro: 'Otro',
}

/** Etiqueta del tipo efectivo. Un code que no está en `sport_types` llega como
 * `null` y se anuncia como tal, no como "Otro": son cosas distintas ("aún no
 * sé qué fue" vs "el usuario dijo que fue otra cosa"). */
export function sportLabel(sport: string | null): string {
  if (sport == null) return 'Sin clasificar'
  return SPORT_LABELS[sport] ?? sport
}

/** Colores elegidos por el usuario, por nombre de deporte (`/api/sports`). */
export type SportStyles = Record<string, string>

/** Color del tipo efectivo, en tres escalones: el que eligió el usuario, el
 * fijo de los tipos que la app conoce, y si no un hash (djb2 sobre el texto
 * normalizado) para que el mismo deporte salga SIEMPRE del mismo color y dos
 * distintos casi nunca coincidan — antes caían todos en el mismo gris. */
export function sportColor(sport: string | null, styles?: SportStyles): string {
  if (sport == null) return SPORT.otro
  // El color que eligió el usuario manda sobre todo lo demás.
  const chosen = styles?.[sport]
  if (chosen) return chosen
  const fixed = SPORT[sport as keyof typeof SPORT]
  if (fixed) return fixed
  const key = sport.trim().toLowerCase()
  let hash = 0
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  return SPORT_RAMP[hash % SPORT_RAMP.length]
}

/** Nombre presentable de cada músculo del vocabulario de `muscle_map.toml`.
 * Vive aquí y no en el body-map porque el detalle de un entreno pinta los
 * mismos músculos y escribía la clave cruda ("biceps", "triceps"). */
const MUSCLE_LABELS: Record<string, string> = {
  pecho: 'Pecho',
  dorsal: 'Dorsal',
  trapecio: 'Trapecio',
  lumbar: 'Lumbar',
  hombro: 'Hombro',
  biceps: 'Bíceps',
  triceps: 'Tríceps',
  antebrazo: 'Antebrazo',
  core: 'Core',
  cuadriceps: 'Cuádriceps',
  femoral: 'Femoral',
  gluteo: 'Glúteo',
  aductor: 'Aductor',
  abductor: 'Abductor',
  gemelo: 'Gemelo',
}

export const muscleLabel = (muscle: string) => MUSCLE_LABELS[muscle] ?? muscle

/** Atajos de la cola de revisión. Solo los dos deportes que
 * la app conoce: 'fuerza' es la que, además de etiquetar, dispara el vínculo
 * con el entreno de Hevy del día. Cualquier otra cosa se escribe a mano
 * ("Otro…" → texto libre): `user_sport` es TEXT, no una lista cerrada. */
export const CLASSIFY_OPTIONS = [
  { value: 'fuerza', label: 'Fuerza' },
  { value: 'voley_playa', label: 'Vóley playa' },
] as const

/** Cubos genéricos: existen como estado, no como deporte. */
const GENERIC_SPORTS = new Set(['auto_ia', 'otro'])

/** Etiquetas que valen para autocompletar cuando escribes un tipo a mano.
 *
 * Fuera los genéricos: "Actividad detectada" es justo de lo que estás saliendo
 * al clasificar, y "Otro" no dice nada. Ordenadas alfabéticamente porque la
 * lista viene del backend por orden de aparición, que no ayuda a nadie. */
export function suggestedSports<T extends { name: string }>(sports: readonly T[]): T[] {
  return sports
    .filter((s) => !GENERIC_SPORTS.has(s.name) && s.name.trim() !== '')
    .sort((a, b) => a.name.localeCompare(b.name, 'es'))
}

export interface ZoneBand extends HrZone {
  label: string
  share: number
  color: string
}

/** Color de la zona `i` de `n`, INTERPOLANDO sobre `ZONE_RAMP`.
 *
 * El strap manda 6 zonas y la rampa tiene 4 colores: redondear al más cercano
 * repetía tonos (dos zonas azules seguidas y dos naranjas), así que la barra
 * apilada se veía como dos bloques y la leyenda no cuadraba con ella. Con la
 * mezcla intermedia cada zona sale de un color distinto y la barra progresa de
 * suave a duro como debe. */
function zoneColor(i: number, n: number): string {
  if (n <= 1) return ZONE_RAMP[0]
  const pos = (i / (n - 1)) * (ZONE_RAMP.length - 1)
  const low = Math.min(Math.floor(pos), ZONE_RAMP.length - 2)
  const frac = pos - low
  if (frac < 0.01) return ZONE_RAMP[low]
  if (frac > 0.99) return ZONE_RAMP[low + 1]
  return `color-mix(in oklab, ${ZONE_RAMP[low + 1]} ${Math.round(frac * 100)}%, ${ZONE_RAMP[low]})`
}

/** Zonas de FC listas para pintar como barra apilada.
 *
 * `threshold` es el techo de la zona, así que el suelo de cada una es el techo
 * de la anterior y la primera se rotula "≤ N". Las zonas de 0 s se descartan:
 * ocupan sitio en la leyenda sin decir nada. */
export function zoneBands(zones: HrZone[]): ZoneBand[] {
  const total = zones.reduce((sum, z) => sum + z.seconds, 0)
  if (total === 0) return []
  return zones
    .map((zone, i) => ({
      ...zone,
      label: i === 0 ? `≤ ${zone.threshold}` : `${zones[i - 1].threshold}–${zone.threshold}`,
      share: zone.seconds / total,
      color: zoneColor(i, zones.length),
    }))
    .filter((zone) => zone.seconds > 0)
}

/** Kilos movidos en la sesión: Σ peso × repeticiones de las series efectivas.
 *
 * El calentamiento queda fuera a propósito: infla la cifra sin ser trabajo, y
 * es justo la serie que uno hace con la barra vacía. `null` cuando la sesión no
 * trae ejercicios (las del strap sin vincular), para no enseñar un 0 que
 * parecería "no levantaste nada". */
export function sessionVolume(exercises: WorkoutExercise[] | undefined): number | null {
  if (!exercises || exercises.length === 0) return null
  return exercises.reduce(
    (total, exercise) =>
      total +
      exercise.sets.reduce(
        (sum, set) =>
          set.set_type === 'warmup' || set.reps == null || set.weight_kg == null
            ? sum
            : sum + set.reps * set.weight_kg,
        0,
      ),
    0,
  )
}

/** Agrupa por día local, del más reciente al más antiguo (el backend ya sirve
 * los workouts en ese orden). */
export function groupByDay(workouts: Workout[]): { day: string; workouts: Workout[] }[] {
  const days: { day: string; workouts: Workout[] }[] = []
  for (const workout of workouts) {
    const day = dayOfTs(workout.start_ts)
    if (days.at(-1)?.day !== day) days.push({ day, workouts: [] })
    days.at(-1)!.workouts.push(workout)
  }
  return days
}

/** Tipos presentes en la lista, para las pastillas del filtro. */
export function sportsPresent(workouts: Workout[]): (string | null)[] {
  const seen = new Set(workouts.map((w) => w.effective_sport))
  return [...seen]
}

/** Filtro que se APLICA de verdad, dado el que eligió el usuario y los tipos
 * presentes en el rango visible.
 *
 * Un filtro que no existe en el rango no debe vaciar la lista: al pasar de mes
 * a semana el tipo elegido puede no haberse hecho esa semana, y como las
 * pastillas solo se pintan habiendo varios tipos, el usuario se quedaba
 * mirando "Sin entrenos" sin nada que pulsar para salir.
 *
 * Se ignora en vez de resetear el estado: al volver al mes su elección sigue
 * puesta, que es lo que espera quien solo estaba cambiando de rango.
 */
export function effectiveFilter(
  filter: string | null,
  sports: (string | null)[],
): string | null {
  return filter !== 'all' && !sports.includes(filter) ? 'all' : filter
}
