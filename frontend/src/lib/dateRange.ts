import { daySpan, isoPlusDays, todayISO } from './date'

export interface DateRange {
  from: string
  to: string
}

export type Preset = 'day' | 'week' | 'month' | 'custom'

/** Ventanas deslizantes ancladas en `to`. Las flechas del RangePicker mueven
 * la ventana justo su propio ancho, así que los tramos tesela sin solaparse
 * (como el carrusel de días/semanas/meses de Zepp). */
export const PRESETS: { id: Exclude<Preset, 'custom'>; label: string; days: number }[] = [
  { id: 'day', label: 'Día', days: 1 },
  { id: 'week', label: 'Semana', days: 7 },
  { id: 'month', label: 'Mes', days: 30 },
]

function presetDays(preset: Preset): number | null {
  return PRESETS.find((p) => p.id === preset)?.days ?? null
}

/** Ventana del preset terminada en `anchor` (por defecto hoy). */
export function presetRange(preset: Exclude<Preset, 'custom'>, anchor: string = todayISO()): DateRange {
  return { from: isoPlusDays(anchor, 1 - presetDays(preset)!), to: anchor }
}

export function defaultRange(preset: Exclude<Preset, 'custom'> = 'day'): { range: DateRange; preset: Preset } {
  return { range: presetRange(preset), preset }
}

/** Desplaza la ventana `dir` pasos (−1 = atrás). En "custom" el paso es el
 * ancho real del rango elegido. Devuelve `null` si el salto se iría al futuro:
 * el llamante usa eso para deshabilitar la flecha. */
export function shiftRange(range: DateRange, preset: Preset, dir: -1 | 1): DateRange | null {
  const step = presetDays(preset) ?? daySpan(range.from, range.to)
  const to = isoPlusDays(range.to, dir * step)
  if (to > todayISO()) return null
  return { from: isoPlusDays(range.from, dir * step), to }
}

const MONTH_DAY: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }

function label(day: string, opts: Intl.DateTimeFormatOptions): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString('es-ES', opts)
}

/** Texto del rango activo: "Hoy" / "Ayer" para el día actual y el anterior
 * (es lo que se lee de un vistazo), fecha o tramo en el resto. */
export function rangeLabel(range: DateRange): string {
  if (range.from === range.to) {
    if (range.to === todayISO()) return 'Hoy'
    if (range.to === isoPlusDays(todayISO(), -1)) return 'Ayer'
    return label(range.to, { weekday: 'short', ...MONTH_DAY })
  }
  const sameMonth = range.from.slice(0, 7) === range.to.slice(0, 7)
  const from = sameMonth ? label(range.from, { day: 'numeric' }) : label(range.from, MONTH_DAY)
  return `${from} – ${label(range.to, MONTH_DAY)}`
}
