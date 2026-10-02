import { useMemo } from 'react'
import { bucketOf, monthGrid, quintileCuts } from '../lib/season'
import { dayOfTs } from '../lib/date'
import { METRIC, rampStep } from '../lib/palette'
import { sportColor, sportLabel } from '../lib/workouts'
import type { SportStyles } from '../lib/workouts'
import type { Workout } from '../lib/types'

const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
const MONTHS = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

export interface CalendarMetric {
  id: string
  label: string
  color: string
  /** Valor del día; `null` = ese día no se midió. */
  valueByDay: Map<string, number | null>
  format: (value: number) => string
}

interface CalendarProps {
  from: string
  to: string
  metric: CalendarMetric
  workouts: Workout[]
  loadByDay: Map<string, number | null>
  selected: string | null
  onSelect: (day: string) => void
  styles?: SportStyles
}

/** El calendario como objeto principal: color = la métrica elegida, barra baja
 * = carga del día y cuadrito = entreno.
 *
 * Los días sin dato salen en hueco perfilado en vez de desaparecer: un mes con
 * agujeros tiene que verse como un mes con agujeros. */
export function Calendar({
  from,
  to,
  metric,
  workouts,
  loadByDay,
  selected,
  onSelect,
  styles,
}: CalendarProps) {
  const cuts = useMemo(() => quintileCuts([...metric.valueByDay.values()]), [metric])
  const maxLoad = useMemo(
    () => Math.max(1, ...[...loadByDay.values()].filter((v): v is number => v != null)),
    [loadByDay],
  )

  const sportsByDay = useMemo(() => {
    const map = new Map<string, string | null>()
    for (const w of workouts) {
      const day = dayOfTs(w.start_ts)
      // Se queda el de más carga: es el que define el día.
      const current = map.get(day)
      if (current === undefined || (w.train_load ?? 0) > 0) map.set(day, w.effective_sport)
    }
    return map
  }, [workouts])

  const months = useMemo(() => {
    const out: { key: string; year: number; month: number }[] = []
    const [fy, fm] = from.split('-').map(Number)
    const [ty, tm] = to.split('-').map(Number)
    for (let y = fy, m = fm; y < ty || (y === ty && m <= tm); m === 12 ? ((y += 1), (m = 1)) : (m += 1)) {
      out.push({ key: `${y}-${m}`, year: y, month: m })
    }
    return out
  }, [from, to])

  return (
    <div className="flex flex-wrap gap-x-8 gap-y-6">
      {months.map(({ key, year, month }) => (
        <div key={key} className="min-w-[240px] flex-1">
          <p className="font-serif text-lg leading-none">
            {MONTHS[month - 1]} <span className="text-ink-muted">{year}</span>
          </p>
          <div className="mt-2 grid grid-cols-7 gap-1 border-t border-hairline pt-2">
            {WEEKDAYS.map((d) => (
              <span key={d} className="text-center font-mono text-[10px] text-ink-muted">
                {d}
              </span>
            ))}
            {monthGrid(year, month).map((cell) => {
              // Fuera del rango elegido no se pinta hueco: "sin registrar" y
              // "no lo estás mirando" son cosas distintas y el hueco mentía.
              if (cell.day < from || cell.day > to) {
                return <span key={cell.day} style={{ gridColumn: cell.col + 1 }} aria-hidden="true" />
              }
              const value = metric.valueByDay.get(cell.day) ?? null
              const load = loadByDay.get(cell.day) ?? 0
              const sport = sportsByDay.get(cell.day)
              const isSelected = cell.day === selected

              return (
                <button
                  key={cell.day}
                  style={{
                    gridColumn: cell.col + 1,
                    backgroundColor: value != null ? rampStep(metric.color, bucketOf(value, cuts)) : undefined,
                  }}
                  onClick={() => onSelect(cell.day)}
                  aria-label={`${cell.day}: ${value != null ? metric.format(value) : 'sin datos'}`}
                  aria-pressed={isSelected}
                  title={`${cell.day} · ${value != null ? metric.format(value) : 'sin datos'}`}
                  className={
                    'relative aspect-square w-full transition-shadow focus-visible:outline-none ' +
                    'focus-visible:ring-2 focus-visible:ring-accent ' +
                    (value == null ? 'border border-hairline ' : '') +
                    (isSelected ? 'ring-2 ring-ink ring-offset-1 ring-offset-page' : '')
                  }
                >
                  {load > 0 && (
                    <span
                      className="absolute inset-x-0 bottom-0 h-[3px]"
                      style={{
                        width: `${Math.max(12, Math.min(100, (load / maxLoad) * 100))}%`,
                        backgroundColor: METRIC.load,
                      }}
                    />
                  )}
                  {sport !== undefined && (
                    <span
                      className="absolute right-0.5 top-0.5 h-1.5 w-1.5"
                      style={{ backgroundColor: sportColor(sport, styles) }}
                      title={sportLabel(sport)}
                    />
                  )}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
