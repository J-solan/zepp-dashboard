import { useMemo } from 'react'
import { areaPath, barsPath, gapPath, linePath } from '../lib/series'
import { daySeries } from '../lib/days'
import { daySpan } from '../lib/date'
import { formatAxisDay } from '../lib/chartFormat'
import { formatNumber } from '../lib/format'
import { METRIC } from '../lib/palette'
import { sportColor, sportLabel } from '../lib/workouts'
import type { SportStyles } from '../lib/workouts'
import { mainSessionPerDay } from '../lib/sleep'
import type { DailyMetrics, SleepSession, Workout } from '../lib/types'
import type { DateRange } from '../lib/dateRange'

// Un carril por métrica, todos sobre el MISMO eje de tiempo: leer una columna
// vertical es leer un día entero. Ese es el motivo de que esto sea un solo SVG
// dibujado a mano y no siete gráficas apiladas.
const X0 = 96
const X1 = 1020
const LANE_H = 38
const PITCH = 54
const TOP = 12
const EVENT_H = 22

type Kind = 'area' | 'line' | 'bars'

interface LaneSpec {
  label: string
  color: string
  kind: Kind
  values: (number | null)[]
  unit?: string
  /** Techo de las barras; por encima se recorta y se rotula el pico. */
  cap?: number
}

/** Dominio con un poco de aire, para que la línea no roce el borde del carril. */
function domainOf(values: (number | null)[]): [number, number] {
  const nums = values.filter((v): v is number => v != null)
  if (nums.length === 0) return [0, 1]
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  if (min === max) return [min - 1, max + 1]
  const pad = (max - min) * 0.12
  return [min - pad, max + pad]
}

const fmt = (n: number) => (Math.abs(n) >= 1000 ? formatNumber(n) : `${Math.round(n)}`)

interface SeriesBoardProps {
  range: DateRange
  daily: DailyMetrics[]
  sessions: SleepSession[]
  workouts: Workout[]
  styles?: SportStyles
}

/** Las siete series del periodo sobre un eje común, más el carril de entrenos.
 *
 * Cada carril lleva su propio mín–máx rotulado a la derecha: los ejes están
 * truncados (si no, readiness viviría en el 80 % superior y no se vería nada)
 * y eso hay que declararlo, no esconderlo.
 */
export function SeriesBoard({ range, daily, sessions, workouts, styles }: SeriesBoardProps) {
  const days = daySpan(range.from, range.to)

  const lanes = useMemo<LaneSpec[]>(() => {
    const pick = (get: (row: DailyMetrics) => number | null) =>
      daySeries(daily, range.to, get, days).map((d) => d.value)

    const nights = mainSessionPerDay(sessions)
    const sleepScores = daySeries(nights, range.to, (s) => s.score, days).map((d) => d.value)

    return [
      { label: 'Readiness', color: METRIC.readiness, kind: 'area', values: pick((r) => r.readiness) },
      { label: 'Sueño', color: METRIC.sleep, kind: 'area', values: sleepScores },
      { label: 'HRV', color: METRIC.bio, kind: 'line', values: pick((r) => r.hrv_ms), unit: 'ms' },
      { label: 'FC reposo', color: METRIC.hr, kind: 'line', values: pick((r) => r.resting_hr), unit: 'bpm' },
      { label: 'Pasos', color: METRIC.steps, kind: 'bars', values: pick((r) => r.steps) },
      { label: 'Carga', color: METRIC.load, kind: 'bars', values: pick((r) => r.train_load), cap: 60 },
      { label: 'Estrés', color: METRIC.stress, kind: 'line', values: pick((r) => r.stress_avg) },
    ]
  }, [daily, sessions, range.to, days])

  const axis = useMemo(
    () => daySeries([], range.to, () => null, days).map((d) => d.day),
    [range.to, days],
  )

  // Un entreno por marca, apiladas por día: el carril contesta "¿qué hice ese
  // día?" sin tener que abrir la pestaña de entrenos.
  const marks = useMemo(() => {
    const byDay = new Map<string, Set<string | null>>()
    for (const w of workouts) {
      const day = new Date(w.start_ts * 1000).toLocaleDateString('sv-SE')
      if (!byDay.has(day)) byDay.set(day, new Set())
      byDay.get(day)!.add(w.effective_sport)
    }
    return axis.flatMap((day, i) =>
      [...(byDay.get(day) ?? [])].slice(0, 3).map((sport, k) => ({
        key: `${day}-${sport}-${k}`,
        x: xAt(i, days) - 3,
        y: eventsTop(lanes.length) + k * 8,
        color: sportColor(sport, styles),
        label: `${day}: ${sportLabel(sport)}`,
      })),
    )
  }, [workouts, axis, days, lanes.length, styles])

  const height = eventsTop(lanes.length) + EVENT_H + 32

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${X1} ${height}`} className="block w-full min-w-[680px]" role="img"
        aria-label="Series diarias del periodo sobre un eje de tiempo común">
        {lanes.map((lane, index) => {
          const top = TOP + index * PITCH
          const [lo, hi] = lane.kind === 'bars' ? [0, lane.cap ?? maxOf(lane.values)] : domainOf(lane.values)
          const x = (i: number) => xAt(i, days)
          const y = (v: number) => top + LANE_H - ((v - lo) / (hi - lo || 1)) * LANE_H
          const nums = lane.values.filter((v): v is number => v != null)

          return (
            <g key={lane.label}>
              <text x="0" y={top + 12} fontSize="12" fill="var(--color-ink)">
                {lane.label}
              </text>
              <text x="0" y={top + 26} fontSize="10" fill="var(--color-ink-muted)" fontFamily="var(--font-mono)">
                {nums.length > 0
                  ? `${fmt(Math.min(...nums))} – ${fmt(Math.max(...nums))}${lane.unit ? ` ${lane.unit}` : ''}`
                  : 'sin datos'}
              </text>

              {lane.kind === 'area' && (
                <>
                  <path d={areaPath(lane.values, x, y, top + LANE_H)} fill={lane.color} opacity="0.16" />
                  <path d={linePath(lane.values, x, y)} fill="none" stroke={lane.color} strokeWidth="1.6" strokeLinejoin="round" />
                </>
              )}
              {lane.kind === 'line' && (
                <>
                  <path d={linePath(lane.values, x, y)} fill="none" stroke={lane.color} strokeWidth="1.6" strokeLinejoin="round" />
                  <path d={gapPath(lane.values, x, y)} fill="none" stroke="var(--color-ink-muted)" strokeWidth="1" strokeDasharray="2 3" opacity="0.5" />
                </>
              )}
              {lane.kind === 'bars' && (
                <path
                  d={barsPath(lane.values, x, {
                    baseY: top + LANE_H,
                    height: LANE_H,
                    max: hi || 1,
                    width: Math.max(3, Math.min(12, (X1 - X0) / days - 4)),
                  })}
                  fill={lane.color}
                />
              )}
              {/* El pico recortado se rotula con su valor real, sobre la
                  barra que lo tiene: la barra sola mentiría sobre cuánto se
                  salió del carril. */}
              {lane.kind === 'bars' && lane.cap != null && nums.some((v) => v > lane.cap!) && (
                <text
                  x={xAt(lane.values.indexOf(Math.max(...nums)), days)}
                  y={top - 2}
                  fontSize="10"
                  textAnchor="middle"
                  fill={lane.color}
                  fontFamily="var(--font-mono)"
                >
                  {fmt(Math.max(...nums))}
                </text>
              )}
            </g>
          )
        })}

        <text x="0" y={eventsTop(lanes.length) + 14} fontSize="12" fill="var(--color-ink)">
          Entrenos
        </text>
        {marks.map((m) => (
          <rect key={m.key} x={m.x} y={m.y} width="6" height="6" fill={m.color}>
            <title>{m.label}</title>
          </rect>
        ))}

        <rect x={X0} y={eventsTop(lanes.length) + EVENT_H} width={X1 - X0} height="1" fill="var(--color-hairline)" />
        {[0, Math.floor(days / 2), days - 1].map((i, k) => (
          <text
            key={i}
            x={xAt(i, days)}
            y={eventsTop(lanes.length) + EVENT_H + 16}
            fontSize="10"
            fill="var(--color-ink-secondary)"
            fontFamily="var(--font-mono)"
            textAnchor={k === 0 ? 'start' : k === 2 ? 'end' : 'middle'}
          >
            {axis[i] ? formatAxisDay(axis[i]) : ''}
          </text>
        ))}
      </svg>
    </div>
  )
}

function xAt(index: number, days: number): number {
  if (days <= 1) return X0
  return X0 + (index * (X1 - X0)) / (days - 1)
}

function eventsTop(laneCount: number): number {
  return TOP + laneCount * PITCH
}

function maxOf(values: (number | null)[]): number {
  const nums = values.filter((v): v is number => v != null)
  return nums.length > 0 ? Math.max(...nums) : 1
}
