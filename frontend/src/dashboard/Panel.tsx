import { useState, type ComponentType } from 'react'
import { useApi } from '../hooks/useApi'
import { useSync } from '../hooks/useSync'
import { useSports } from '../hooks/useSports'
import { Button } from '../components/Button'
import { SyncBanner } from '../components/SyncBanner'
import { AlertIcon, SpinnerIcon } from '../components/icons'
import { DayRail } from './DayRail'
import { SeriesBoard } from './SeriesBoard'
import { Crosses } from './Crosses'
import { HrDetail } from './HrDetail'
import { StressDetail } from './StressDetail'
import { SleepDetail } from './SleepDetail'
import { HybridChargeDetail } from './HybridChargeDetail'
import { isoDaysAgo, todayISO } from '../lib/date'
import { daySpan } from '../lib/date'
import { formatTooltipDay } from '../lib/chartFormat'
import type { TabProps } from '../App'
import type { DailyMetrics, Overview, SleepSession, Workout } from '../lib/types'

/** Ventana fija de referencia para las bandas del día. No es el rango elegido
 * a propósito: "por encima de tu banda" tiene que significar lo mismo se esté
 * mirando un día o tres meses. */
const BASELINE_DAYS = 30

const DETAILS: { id: string; label: string; Component: ComponentType<TabProps> }[] = [
  { id: 'hr', label: 'FC', Component: HrDetail },
  { id: 'stress', label: 'Estrés', Component: StressDetail },
  { id: 'sleep', label: 'Sueño', Component: SleepDetail },
  { id: 'bio', label: 'BioCharge', Component: HybridChargeDetail },
]

const chipClass = (active: boolean) =>
  'rounded-sm px-3 py-1 text-sm transition-colors duration-150 focus-visible:outline-none ' +
  'focus-visible:ring-2 focus-visible:ring-accent ' +
  (active ? 'bg-ink font-medium text-page' : 'text-ink-secondary hover:text-ink')

/** Vista principal: el día contra tu propio historial a la izquierda y el
 * periodo entero, serie a serie, a la derecha.
 *
 * Las series intradía (FC, estrés, biocharge y el hipnograma) viven en su
 * detalle, que se abre bajo el tablero. No van en acordeón: con una sola
 * abierta a la vez, comparar dos era abrir, cerrar y recordar. */
export function Panel({ range }: TabProps) {
  const [detail, setDetail] = useState<string | null>(null)

  const baselineFrom = isoDaysAgo(BASELINE_DAYS - 1)
  const today = todayISO()

  const { data: overview, loading, error, refetch } = useApi<Overview>('/api/overview')
  const { isSyncing, triggerError, trigger } = useSync(refetch)
  const { styles } = useSports()

  const { data: dailyRange } = useApi<DailyMetrics[]>(`/api/daily?from=${range.from}&to=${range.to}`)
  const { data: dailyBaseline } = useApi<DailyMetrics[]>(`/api/daily?from=${baselineFrom}&to=${today}`)
  const { data: sleepRange } = useApi<SleepSession[]>(`/api/sleep?from=${range.from}&to=${range.to}`)
  const { data: sleepBaseline } = useApi<SleepSession[]>(`/api/sleep?from=${baselineFrom}&to=${today}`)
  const { data: workouts } = useApi<Workout[]>(`/api/workouts?from=${range.from}&to=${range.to}`)

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-ink-secondary">
        <SpinnerIcon className="h-4 w-4" />
        <p className="text-sm">Cargando…</p>
      </div>
    )
  }

  if (error && !overview) {
    return (
      <div className="flex flex-col items-center gap-3 p-8 text-center">
        <AlertIcon className="h-6 w-6 text-err" />
        <p className="text-sm text-ink-secondary">No se pudo cargar el resumen: {error}</p>
        <Button variant="ghost" onClick={refetch}>
          Reintentar
        </Button>
      </div>
    )
  }

  if (!overview) return null

  const lastWithData = [...(dailyBaseline ?? [])].reverse().find((d) => d.readiness != null || d.steps != null)
  const ActiveDetail = DETAILS.find((d) => d.id === detail)?.Component

  return (
    <div className="flex flex-col gap-6 p-4">
      <SyncBanner
        isSyncing={isSyncing}
        triggerError={triggerError}
        trigger={trigger}
        lastSync={overview.last_sync}
      />

      <div className="grid gap-8 lg:grid-cols-[300px_1fr]">
        <section className="flex flex-col gap-4">
          <div>
            <p className="text-label uppercase text-ink-muted">Último día con datos</p>
            <p className="font-serif text-2xl leading-tight">
              {lastWithData ? formatTooltipDay(lastWithData.day) : 'Sin datos todavía'}
            </p>
          </div>
          <DayRail daily={dailyBaseline ?? []} sessions={sleepBaseline ?? []} />
        </section>

        <section className="flex min-w-0 flex-col gap-4">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-label uppercase text-ink-muted">
              {daySpan(range.from, range.to)} días · una columna es un día
            </p>
            <p className="text-xs text-ink-muted">Cada serie lleva su propio mín–máx a la derecha</p>
          </div>

          <SeriesBoard
            range={range}
            daily={dailyRange ?? []}
            sessions={sleepRange ?? []}
            workouts={workouts ?? []}
            styles={styles}
          />

          <Crosses daily={dailyRange ?? []} sessions={sleepRange ?? []} />
        </section>
      </div>

      <section className="flex flex-col gap-3 border-t border-hairline pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-label mr-2 uppercase text-ink-muted">Detalle intradía</p>
          {DETAILS.map((d) => (
            <button
              key={d.id}
              className={chipClass(detail === d.id)}
              aria-pressed={detail === d.id}
              onClick={() => setDetail((cur) => (cur === d.id ? null : d.id))}
            >
              {d.label}
            </button>
          ))}
        </div>
        {ActiveDetail && (
          <div className="animate-card-expand">
            <ActiveDetail range={range} />
          </div>
        )}
      </section>
    </div>
  )
}
