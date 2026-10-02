import { useMemo } from 'react'
import { barsPath } from '../lib/series'
import { daySeries } from '../lib/days'
import { daySpan } from '../lib/date'
import { formatAxisDay } from '../lib/chartFormat'
import { METRIC } from '../lib/palette'
import type { DailyMetrics } from '../lib/types'
import type { DateRange } from '../lib/dateRange'

const W = 900
const H = 56

interface LoadStripProps {
  range: DateRange
  daily: DailyMetrics[]
  /** Día de la sesión abierta; se marca para situarla dentro del periodo. */
  selectedDay: string | null
}

/** Carga diaria del periodo, con el día de la sesión abierta marcado.
 *
 * Contesta "¿esto fue mucho para mí?", que es la pregunta que una cifra suelta
 * de carga no puede responder. */
export function LoadStrip({ range, daily, selectedDay }: LoadStripProps) {
  const days = daySpan(range.from, range.to)

  const { values, axis } = useMemo(() => {
    const series = daySeries(daily, range.to, (r) => r.train_load, days)
    return { values: series.map((d) => d.value), axis: series.map((d) => d.day) }
  }, [daily, range.to, days])

  const x = (i: number) => (days <= 1 ? W / 2 : (i * W) / (days - 1))
  const max = Math.max(1, ...values.filter((v): v is number => v != null))
  const width = Math.max(3, Math.min(14, W / days - 4))
  const selectedIndex = selectedDay ? axis.indexOf(selectedDay) : -1
  const selectedValue = selectedIndex >= 0 ? values[selectedIndex] : null

  if (values.every((v) => v == null || v === 0)) return null

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-label uppercase text-ink-muted">Carga del periodo · cada barra un día</p>
        {selectedValue != null && (
          <p className="font-mono text-xs text-ink-secondary">
            la sesión abierta cae en un día de {selectedValue}
          </p>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="block w-full" role="img" aria-label="Carga diaria del periodo">
        {/* La barra del día abierto va detrás y a toda altura: sitúa el día sin
            competir con la barra de su carga. */}
        {selectedIndex >= 0 && (
          <rect x={x(selectedIndex) - width / 2 - 2} y="0" width={width + 4} height={H} fill="var(--color-raised)" />
        )}
        <path d={barsPath(values, x, { baseY: H, height: H, max, width })} fill={METRIC.load} />
        <rect x="0" y={H} width={W} height="1" fill="var(--color-hairline)" />
        <text x="0" y={H + 14} fontSize="10" fill="var(--color-ink-muted)" fontFamily="var(--font-mono)">
          {formatAxisDay(range.from)}
        </text>
        <text
          x={W}
          y={H + 14}
          fontSize="10"
          textAnchor="end"
          fill="var(--color-ink-muted)"
          fontFamily="var(--font-mono)"
        >
          {formatAxisDay(range.to)} · máx {max}
        </text>
      </svg>
    </div>
  )
}
