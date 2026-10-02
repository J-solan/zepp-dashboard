import { APP_TZ } from './date'

const DAY_S = 86400

// Pasos intradía para los ticks del eje X. Se elige el más fino que no pase de
// MAX_TICKS marcas en el tramo visible, así el zoom va bajando solo de 3 h a
// 15 min o a 5 min sin que haya que tocar nada.
const SUB_DAY_STEPS = [300, 900, 1800, 3600, 2 * 3600, 3 * 3600, 6 * 3600, 12 * 3600]
const MAX_TICKS = 8

export interface TimeAxis {
  ticks: number[]
  format: (ts: number) => string
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', timeZone: APP_TZ })
}

function formatDay(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', timeZone: APP_TZ })
}

/** Ticks del eje X para el tramo visible `[start, end]` (unix s).
 *
 * `dayStarts` son las medianoches LOCALES del rango: se usan como marcas
 * directas en multi-día (exactas también en los días de cambio de horario, que
 * no duran 86400 s) y como anclaje de la rejilla intradía, para que las horas
 * caigan en :00 y no en el primer dato que hubiera. */
export function timeAxis(start: number, end: number, dayStarts: number[]): TimeAxis {
  if (end - start > 1.5 * DAY_S) {
    const visible = dayStarts.filter((ts) => ts >= start && ts <= end)
    const every = Math.max(Math.ceil(visible.length / MAX_TICKS), 1)
    return { ticks: visible.filter((_, i) => i % every === 0), format: formatDay }
  }

  const step = SUB_DAY_STEPS.find((s) => (end - start) / s <= MAX_TICKS) ?? DAY_S
  const anchor = dayStarts[0] ?? start
  const ticks: number[] = []
  for (let t = anchor + Math.ceil((start - anchor) / step) * step; t < end; t += step) ticks.push(t)
  return { ticks, format: formatTime }
}

export function formatTooltipTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: APP_TZ,
  })
}

export function formatTooltipDay(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString('es-ES', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
  })
}

export function formatAxisDay(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' })
}
