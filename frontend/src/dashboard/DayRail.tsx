import { Hypnogram } from '../components/Hypnogram'
import { quantiles, type Band } from '../lib/baseline'
import { formatDuration, formatNumber } from '../lib/format'
import { METRIC } from '../lib/palette'
import { mainSessionPerDay } from '../lib/sleep'
import type { DailyMetrics, SleepSession } from '../lib/types'

const STRIP_WIDTH = 264

interface Row {
  label: string
  color: string
  value: number | null
  /** Texto del valor; el número crudo solo sirve para situarlo en la banda. */
  text: string
  sub?: string
  band: Band | null
}

/** Dónde cae `value` dentro de [min, max] de la banda, en px de la pista. */
function at(value: number, band: Band): number {
  const span = band.max - band.min
  if (span === 0) return STRIP_WIDTH / 2
  return ((value - band.min) / span) * STRIP_WIDTH
}

function verdict(value: number, band: Band): string {
  const banda = `banda ${Math.round(band.p25)}–${Math.round(band.p75)}`
  if (value > band.p75) return `Por encima de tu ${banda}`
  if (value < band.p25) return `Por debajo de tu ${banda}`
  return `Dentro de tu ${banda}`
}

function Strip({ row }: { row: Row }) {
  const { band, value } = row
  if (band == null || value == null) return null
  // Radio del punto: pegado al extremo se sale de la pista y parece un error.
  const cx = Math.min(Math.max(at(value, band), 5), STRIP_WIDTH - 5)
  const from = at(band.p25, band)
  const to = at(band.p75, band)

  return (
    <svg viewBox={`0 0 ${STRIP_WIDTH} 15`} className="mt-1 block w-full" role="presentation">
      <rect x="0" y="6" width={STRIP_WIDTH} height="3" fill="var(--color-grid)" />
      <rect x={from} y="4" width={Math.max(to - from, 1)} height="7" fill={row.color} opacity="0.22" />
      <rect x={at(band.median, band)} y="2" width="1.5" height="11" fill={row.color} opacity="0.7" />
      <circle cx={cx} cy="7.5" r="4.5" fill={row.color} />
    </svg>
  )
}

interface DayRailProps {
  /** Ventana de referencia (los últimos 30 días), no el rango elegido: la
   * banda tiene que significar lo mismo se esté mirando lo que se esté
   * mirando. */
  daily: DailyMetrics[]
  sessions: SleepSession[]
}

/** El día contra tu propio historial.
 *
 * Cada métrica va sobre la distribución de tus últimos 30 días: la caja es la
 * mitad central, la marca la mediana y el punto, hoy. Un "92" a secas no dice
 * si es alto; encima de su banda, sí.
 *
 * Enseña el último día CON DATO y no la fecha de hoy: hasta que no entra el
 * primer sync del día, "hoy" está vacío y una columna de guiones no es
 * información. */
export function DayRail({ daily, sessions }: DayRailProps) {
  const nights = mainSessionPerDay(sessions)
  const last = [...daily].reverse().find((d) => d.readiness != null || d.steps != null || d.resting_hr != null)
  if (!last) {
    return <p className="text-sm text-ink-secondary">Todavía no hay ningún día con datos en la ventana.</p>
  }

  const night = nights.find((s) => s.day === last.day) ?? null
  const nightMinutes = night ? (night.end_ts - night.start_ts) / 60 : null

  const rows: Row[] = [
    {
      label: 'Readiness',
      color: METRIC.readiness,
      value: last.readiness,
      text: last.readiness != null ? `${last.readiness}` : '–',
      sub: '/100',
      band: quantiles(daily.map((d) => d.readiness)),
    },
    {
      label: 'HRV',
      color: METRIC.bio,
      value: last.hrv_ms,
      text: last.hrv_ms != null ? `${Math.round(last.hrv_ms)}` : '–',
      sub: 'ms',
      band: quantiles(daily.map((d) => d.hrv_ms)),
    },
    {
      label: 'FC en reposo',
      color: METRIC.hr,
      value: last.resting_hr,
      text: last.resting_hr != null ? `${last.resting_hr}` : '–',
      sub: 'bpm',
      band: quantiles(daily.map((d) => d.resting_hr)),
    },
    {
      label: 'Sueño',
      color: METRIC.sleep,
      value: night?.score ?? null,
      text: night?.score != null ? `${night.score}` : '–',
      sub: nightMinutes != null ? formatDuration(nightMinutes) : undefined,
      band: quantiles(nights.map((s) => s.score)),
    },
    {
      label: 'Pasos',
      color: METRIC.steps,
      value: last.steps,
      text: last.steps != null ? formatNumber(last.steps) : '–',
      band: quantiles(daily.map((d) => d.steps)),
    },
    {
      label: 'Carga de entreno',
      color: METRIC.load,
      value: last.train_load,
      text: last.train_load != null ? `${last.train_load}` : '–',
      band: quantiles(daily.map((d) => d.train_load)),
    },
  ]

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4">
        {rows.map((row) => (
          <div key={row.label}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm">{row.label}</span>
              <span>
                <span className="font-mono text-lg tabular-nums">{row.text}</span>
                {row.sub && <span className="font-mono text-xs text-ink-muted"> {row.sub}</span>}
              </span>
            </div>
            <Strip row={row} />
            <p className="mt-0.5 text-xs text-ink-secondary">
              {row.value != null && row.band ? verdict(row.value, row.band) : 'Sin dato en este día'}
            </p>
          </div>
        ))}
      </div>

      {night && (
        <div className="border-t border-hairline pt-4">
          <p className="text-label uppercase text-ink-muted">La noche</p>
          <div className="mt-2">
            <Hypnogram session={night} />
          </div>
        </div>
      )}
    </div>
  )
}
