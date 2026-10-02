import { useMemo, useState } from 'react'
import { AsyncState } from '../components/AsyncState'
import { useApi } from '../hooks/useApi'
import { useSports } from '../hooks/useSports'
import { Calendar, type CalendarMetric } from '../temporada/Calendar'
import { WeekdayPattern } from '../temporada/WeekdayPattern'
import { findings, monthlySummary, weekdayMedians } from '../lib/season'
import { mainSessionPerDay } from '../lib/sleep'
import { dayOfTs } from '../lib/date'
import { formatClock, formatDuration, formatNumber } from '../lib/format'
import { formatTooltipDay } from '../lib/chartFormat'
import { METRIC, rampStep } from '../lib/palette'
import { sportColor, sportLabel } from '../lib/workouts'
import type { TabProps } from '../App'
import type { DailyMetrics, SleepSession, Workout } from '../lib/types'

const MONTH_LABEL = (month: string) => {
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

const int = (v: number) => `${Math.round(v)}`
const thousands = (v: number) => formatNumber(v)

/** La vista de lejos: el calendario del periodo, lo que se ve desde arriba y
 * el mes a mes. Contesta "¿qué forma tiene mi temporada?", que es la pregunta
 * que el Panel no puede contestar mirando treinta días. */
export function Temporada({ range }: TabProps) {
  const [metricId, setMetricId] = useState('readiness')
  const [selected, setSelected] = useState<string | null>(null)

  const { data: daily, loading, error, refetch } = useApi<DailyMetrics[]>(
    `/api/daily?from=${range.from}&to=${range.to}`,
  )
  const { data: sleep } = useApi<SleepSession[]>(`/api/sleep?from=${range.from}&to=${range.to}`)
  const { data: workouts } = useApi<Workout[]>(`/api/workouts?from=${range.from}&to=${range.to}`)
  const { styles } = useSports()

  const rows = useMemo(() => daily ?? [], [daily])
  const nights = useMemo(() => mainSessionPerDay(sleep ?? []), [sleep])
  const sessions = useMemo(() => workouts ?? [], [workouts])

  const metrics = useMemo<CalendarMetric[]>(() => {
    const fromDaily = (pick: (r: DailyMetrics) => number | null) =>
      new Map(rows.map((r) => [r.day, pick(r)]))
    return [
      { id: 'readiness', label: 'Readiness', color: METRIC.readiness, valueByDay: fromDaily((r) => r.readiness), format: int },
      { id: 'sleep', label: 'Sueño', color: METRIC.sleep, valueByDay: new Map(nights.map((s) => [s.day, s.score])), format: int },
      { id: 'load', label: 'Carga', color: METRIC.load, valueByDay: fromDaily((r) => r.train_load), format: int },
      { id: 'hrv', label: 'HRV', color: METRIC.bio, valueByDay: fromDaily((r) => r.hrv_ms), format: int },
      { id: 'steps', label: 'Pasos', color: METRIC.steps, valueByDay: fromDaily((r) => r.steps), format: thousands },
    ]
  }, [rows, nights])

  const metric = metrics.find((m) => m.id === metricId)!
  const loadByDay = useMemo(() => new Map(rows.map((r) => [r.day, r.train_load])), [rows])

  const medians = useMemo(() => {
    const source = metric.id === 'sleep' ? nights : rows
    return weekdayMedians(source as { day: string }[], (row) => metric.valueByDay.get(row.day) ?? null)
  }, [metric, nights, rows])

  const summary = useMemo(() => monthlySummary(rows, nights, sessions), [rows, nights, sessions])
  const hallazgos = useMemo(() => findings(rows, nights, sessions), [rows, nights, sessions])

  const dayRow = rows.find((r) => r.day === selected)
  const dayNight = nights.find((s) => s.day === selected)
  const daySessions = sessions.filter((w) => dayOfTs(w.start_ts) === selected)

  return (
    <div className="flex flex-col gap-6 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-label mr-2 uppercase text-ink-muted">Colorear por</p>
        {metrics.map((m) => (
          <button
            key={m.id}
            onClick={() => setMetricId(m.id)}
            aria-pressed={m.id === metricId}
            className={
              'rounded-sm px-3 py-1 text-sm transition-colors duration-150 focus-visible:outline-none ' +
              'focus-visible:ring-2 focus-visible:ring-accent ' +
              (m.id === metricId ? 'bg-ink font-medium text-page' : 'text-ink-secondary hover:text-ink')
            }
          >
            {m.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-ink-muted">
          La escala se normaliza contra tu propio periodo, no contra un máximo de fábrica
        </span>
      </div>

      <AsyncState
        loading={loading && !daily}
        error={error}
        isEmpty={rows.length === 0}
        emptyMessage="Sin días registrados en este rango."
        errorPrefix="No se pudo cargar la temporada"
        onRetry={refetch}
      >
        <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
          <div className="flex min-w-0 flex-col gap-6">
            <Calendar
              from={range.from}
              to={range.to}
              metric={metric}
              workouts={sessions}
              loadByDay={loadByDay}
              selected={selected}
              onSelect={setSelected}
              styles={styles}
            />

            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-hairline pt-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-ink-muted">bajo</span>
                {[0, 1, 2, 3, 4].map((b) => (
                  <span
                    key={b}
                    className="inline-block h-3 w-6"
                    style={{ backgroundColor: rampStep(metric.color, b) }}
                  />
                ))}
                <span className="font-mono text-[11px] text-ink-muted">alto · {metric.label.toLowerCase()}</span>
              </div>
              <div className="flex flex-wrap items-center gap-4 text-xs text-ink-secondary">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-1 w-4" style={{ backgroundColor: METRIC.load }} />
                  carga del día
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 border border-hairline" />
                  sin registrar
                </span>
              </div>
            </div>

            <div className="border-t border-hairline pt-4">
              <WeekdayPattern
                medians={medians}
                color={metric.color}
                label={metric.label}
                format={metric.format}
              />
            </div>
          </div>

          <div className="flex flex-col gap-6">
            <div>
              <p className="text-label uppercase text-ink-muted">Día abierto</p>
              <p className="font-serif text-2xl leading-tight">
                {selected ? formatTooltipDay(selected) : 'Toca un día del calendario'}
              </p>
              {dayRow && (
                <div className="mt-3 grid grid-cols-3 gap-3">
                  <Stat label="Readiness" value={dayRow.readiness} />
                  <Stat label="Sueño" value={dayNight?.score ?? null} />
                  <Stat
                    label="Dormido"
                    text={dayNight ? formatDuration((dayNight.end_ts - dayNight.start_ts) / 60) : '–'}
                  />
                  <Stat label="HRV" value={dayRow.hrv_ms} />
                  <Stat label="FC reposo" value={dayRow.resting_hr} />
                  <Stat label="Pasos" text={dayRow.steps != null ? thousands(dayRow.steps) : '–'} />
                </div>
              )}
              {selected && !dayRow && (
                <p className="mt-2 text-sm text-ink-secondary">Ese día no tiene ningún dato registrado.</p>
              )}
              {daySessions.length > 0 && (
                <div className="mt-4 flex flex-col gap-1.5 border-t border-hairline pt-3">
                  {daySessions.map((w) => (
                    <div key={w.id} className="flex items-baseline gap-2 text-xs">
                      <span className="w-10 font-mono text-ink-secondary">{formatClock(w.start_ts)}</span>
                      <span className="flex-1 truncate" style={{ color: sportColor(w.effective_sport, styles) }}>
                        {sportLabel(w.effective_sport)}
                      </span>
                      <span className="font-mono text-ink-secondary">
                        {formatDuration((w.end_ts - w.start_ts) / 60)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="border-t border-ink pt-4">
              <p className="text-label uppercase text-ink-muted">Lo que se ve desde arriba</p>
              <div className="mt-3 flex flex-col gap-4">
                {hallazgos.length === 0 && (
                  <p className="text-sm text-ink-secondary">Aún no hay periodo suficiente para sacar conclusiones.</p>
                )}
                {hallazgos.map((f) => (
                  <div key={f.id} className="flex gap-3 border-t border-hairline pt-3 first:border-0 first:pt-0">
                    <span className="w-12 shrink-0 text-right font-mono text-lg text-accent">{f.figure}</span>
                    <div>
                      <p className="font-serif text-base leading-snug">{f.title}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-ink-secondary">{f.body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <section className="border-t border-ink pt-4">
          <p className="text-label uppercase text-ink-muted">
            Mes a mes · medianas, salvo carga y entrenos, que suman
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="text-label uppercase text-ink-muted">
                  <th className="py-1 text-left font-medium">Mes</th>
                  {['Días', 'Readiness', 'Sueño', 'Dormido', 'HRV', 'FC reposo', 'Carga', 'Entrenos'].map((h) => (
                    <th key={h} className="py-1 text-right font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {summary.map((m) => (
                  <tr key={m.month} className="border-t border-hairline">
                    <td className="py-2 font-serif text-base">{MONTH_LABEL(m.month)}</td>
                    <td className="py-2 text-right text-ink-secondary">{m.days}</td>
                    <td className="py-2 text-right">{m.readiness ?? '–'}</td>
                    <td className="py-2 text-right">{m.sleep ?? '–'}</td>
                    <td className="py-2 text-right">
                      {m.sleepMinutes != null ? formatDuration(m.sleepMinutes) : '–'}
                    </td>
                    <td className="py-2 text-right">{m.hrv != null ? Math.round(m.hrv) : '–'}</td>
                    <td className="py-2 text-right">{m.restingHr ?? '–'}</td>
                    <td className="py-2 text-right">{m.load}</td>
                    <td className="py-2 text-right">{m.workouts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </AsyncState>
    </div>
  )
}

function Stat({ label, value, text }: { label: string; value?: number | null; text?: string }) {
  return (
    <div>
      <p className="text-label uppercase text-ink-muted">{label}</p>
      <p className="font-mono text-xl tabular-nums">
        {text ?? (value != null ? Math.round(value) : '–')}
      </p>
    </div>
  )
}
