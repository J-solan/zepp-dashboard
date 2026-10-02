import { quantiles } from './baseline'
import { dayOfTs } from './date'
import { pearson } from './stats'
import type { DailyMetrics, SleepSession, Workout } from './types'

/** Lo que solo se ve de lejos: la forma del mes, el patrón de la semana y los
 * tramos que no se notan mirando un día. Todo puro y sobre los datos que ya
 * hay; no hace falta ningún endpoint nuevo. */

export interface GridCell {
  day: string
  /** Columna 0 = lunes. */
  col: number
  row: number
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Rejilla de un mes con el lunes como primera columna.
 *
 * A mediodía UTC para calcular el día de la semana: con medianoche, cualquier
 * huso al oeste devuelve el día anterior y el mes entero sale corrido. */
export function monthGrid(year: number, month: number): GridCell[] {
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const firstCol = (new Date(Date.UTC(year, month - 1, 1, 12)).getUTCDay() + 6) % 7
  return Array.from({ length: days }, (_, i) => ({
    day: `${year}-${pad(month)}-${pad(i + 1)}`,
    col: (firstCol + i) % 7,
    row: Math.floor((firstCol + i) / 7),
  }))
}

/** Los cuatro cortes que parten TU serie en cinco tramos.
 *
 * Contra el propio periodo y no contra una escala de fábrica: así el color
 * dice "alto para ti", que es lo único que se puede afirmar. */
export function quintileCuts(values: readonly (number | null | undefined)[]): number[] {
  const sorted = values.filter((v): v is number => v != null).sort((a, b) => a - b)
  if (sorted.length === 0) return []
  return [0.2, 0.4, 0.6, 0.8].map((p) => sorted[Math.floor((sorted.length - 1) * p)])
}

export function bucketOf(value: number, cuts: readonly number[]): number {
  let bucket = 0
  while (bucket < cuts.length && value >= cuts[bucket]) bucket++
  return bucket
}

/** Mediana por día de la semana, de lunes a domingo. */
export function weekdayMedians<T extends { day: string }>(
  rows: readonly T[],
  pick: (row: T) => number | null,
): (number | null)[] {
  const buckets: number[][] = Array.from({ length: 7 }, () => [])
  for (const row of rows) {
    const value = pick(row)
    if (value == null) continue
    const [y, m, d] = row.day.split('-').map(Number)
    buckets[(new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay() + 6) % 7].push(value)
  }
  return buckets.map((values) => quantiles(values)?.median ?? null)
}

export interface MonthSummary {
  month: string
  days: number
  readiness: number | null
  sleep: number | null
  sleepMinutes: number | null
  hrv: number | null
  restingHr: number | null
  /** La carga SUMA; las demás columnas son medianas. */
  load: number
  workouts: number
}

export function monthlySummary(
  daily: readonly DailyMetrics[],
  nights: readonly SleepSession[],
  workouts: readonly Workout[],
): MonthSummary[] {
  const months = new Map<string, DailyMetrics[]>()
  for (const row of daily) {
    const key = row.day.slice(0, 7)
    if (!months.has(key)) months.set(key, [])
    months.get(key)!.push(row)
  }

  return [...months.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, rows]) => {
      const monthNights = nights.filter((s) => s.day.startsWith(month))
      const median = (values: (number | null)[]) => quantiles(values)?.median ?? null
      return {
        month,
        days: rows.length,
        readiness: median(rows.map((r) => r.readiness)),
        sleep: median(monthNights.map((s) => s.score)),
        sleepMinutes: median(monthNights.map((s) => (s.end_ts - s.start_ts) / 60)),
        hrv: median(rows.map((r) => r.hrv_ms)),
        restingHr: median(rows.map((r) => r.resting_hr)),
        load: rows.reduce((sum, r) => sum + (r.train_load ?? 0), 0),
        workouts: workouts.filter((w) => dayOfTs(w.start_ts).startsWith(month)).length,
      }
    })
}

export interface Finding {
  id: string
  /** La cifra que abre el hallazgo. */
  figure: string
  title: string
  body: string
}

/** Mínimo para que un tramo merezca contarse: con menos, es ruido. */
const MIN_RUN = 3

function longestRun(flags: boolean[]): { length: number; end: number } {
  let best = { length: 0, end: -1 }
  let run = 0
  flags.forEach((ok, i) => {
    run = ok ? run + 1 : 0
    if (run > best.length) best = { length: run, end: i }
  })
  return best
}

const dayLabel = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString('es-ES', { day: 'numeric', month: 'long' })

/** Los hallazgos del periodo. Cada uno se calla si no tiene base: mejor tres
 * frases ciertas que cinco huecos rellenos. */
export function findings(
  daily: readonly DailyMetrics[],
  nights: readonly SleepSession[],
  workouts: readonly Workout[],
): Finding[] {
  const rows = [...daily].sort((a, b) => a.day.localeCompare(b.day))
  const out: Finding[] = []
  if (rows.length === 0) return out

  const readinessBand = quantiles(rows.map((r) => r.readiness))
  if (readinessBand) {
    const streak = longestRun(rows.map((r) => r.readiness != null && r.readiness > readinessBand.median))
    if (streak.length >= MIN_RUN) {
      out.push({
        id: 'racha',
        figure: `${streak.length} d`,
        title: 'Tu racha más larga por encima de la mediana',
        body: `${streak.length} días seguidos de readiness por encima de ${Math.round(readinessBand.median)}, hasta el ${dayLabel(rows[streak.end].day)}.`,
      })
    }
  }

  const trained = new Set(workouts.map((w) => dayOfTs(w.start_ts)))
  const gap = longestRun(rows.map((r) => !trained.has(r.day)))
  if (gap.length >= MIN_RUN) {
    const from = rows[gap.end - gap.length + 1].day
    out.push({
      id: 'parón',
      figure: `${gap.length} d`,
      title: 'El tramo más largo sin entrenar',
      body: `Del ${dayLabel(from)} al ${dayLabel(rows[gap.end].day)} no hay ninguna sesión registrada.`,
    })
  }

  const hardest = workouts.reduce<Workout | null>(
    (best, w) => ((w.train_load ?? 0) > (best?.train_load ?? 0) ? w : best),
    null,
  )
  if (hardest?.train_load != null && hardest.train_load > 0) {
    out.push({
      id: 'dura',
      figure: `${hardest.train_load}`,
      title: 'La sesión más dura del periodo',
      body: `El ${dayLabel(dayOfTs(hardest.start_ts))}, con carga ${hardest.train_load}. El resto del periodo se mueve muy por debajo.`,
    })
  }

  // El cruce que casi nadie enseña: dormir MÁS no es lo mismo que recuperar.
  const byDay = new Map(rows.map((r) => [r.day, r]))
  const paired = nights.filter((s) => byDay.has(s.day))
  const r = pearson(
    paired.map((s) => (s.end_ts - s.start_ts) / 60),
    paired.map((s) => byDay.get(s.day)!.readiness),
  )
  if (r != null) {
    const strong = Math.abs(r) >= 0.4
    out.push({
      id: 'cruce',
      figure: r.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      title: strong ? 'Dormir más sí te acompaña el readiness' : 'Dormir más no te sube el readiness',
      body: `Correlación de ${r.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} entre horas dormidas y readiness en ${paired.length} noches. Correlación, no causa.`,
    })
  }

  return out
}
