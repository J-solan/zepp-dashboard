import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AsyncState } from '../components/AsyncState'
import { BellIcon, CloseIcon, PlusIcon, TagIcon } from '../components/icons'
import { useApi } from '../hooks/useApi'
import { useReviewQueue } from '../hooks/useReviewQueue'
import { useSports } from '../hooks/useSports'
import { formatTooltipDay } from '../lib/chartFormat'
import { dayOfTs } from '../lib/date'
import { formatClock, formatDuration, formatNumber } from '../lib/format'
import type { TabProps } from '../App'
import { effectiveFilter, groupByDay, sessionVolume, sportColor, sportLabel, sportsPresent } from '../lib/workouts'
import { BodyMap } from '../workouts/BodyMap'
import { NewWorkout } from '../workouts/NewWorkout'
import { ReviewQueue } from '../workouts/ReviewQueue'
import { SportLabels } from '../workouts/SportLabels'
import { WorkoutRow } from '../workouts/WorkoutRow'
import { WorkoutDetail } from '../workouts/WorkoutDetail'
import { LoadStrip } from '../workouts/LoadStrip'
import type { DailyMetrics, Workout } from '../lib/types'

type Filter = 'all' | string | null
type View = 'historial' | 'musculos'

const VIEWS: { id: View; label: string }[] = [
  { id: 'historial', label: 'Historial' },
  { id: 'musculos', label: 'Músculos' },
]

// Mismo patrón que las pestañas del RangePicker: el activo se marca con un
// escalón de gris, no con el acento — el acento se reserva para el dato.
const segmentClass = (active: boolean) =>
  'shrink-0 border-b-2 pb-1 text-sm transition-colors duration-150 ' +
  (active ? 'border-metric-readiness font-medium text-ink' : 'border-transparent text-ink-secondary hover:text-ink')

const pillClass = (active: boolean) =>
  'shrink-0 rounded-sm border px-2.5 py-0.5 text-label uppercase transition-colors duration-150 ' +
  (active ? 'border-transparent text-page' : 'border-hairline text-ink-secondary hover:text-ink')

/** Panel de la campana. `<dialog>` nativo y no un div flotante: la capa
 * superior, el cierre con Escape, el clic fuera y el foco atrapado ya los da
 * el navegador. Va anclado abajo (sheet) porque es donde llega el pulgar. */
function Sheet({ open, onClose, title, children }: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
      aria-label={title}
      className="fixed inset-0 mb-0 ml-auto mr-auto mt-auto max-h-[85svh] w-full max-w-2xl
                 overflow-y-auto rounded-t-card border-x border-t border-hairline bg-page p-0
                 text-ink backdrop:bg-black/60"
    >
      {/* El padding va DENTRO y no en el <dialog>: el clic en el fondo se
          detecta porque su target es el propio dialog, así que un padding
          suyo cerraría el panel al tocar cualquier hueco entre tarjetas. */}
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-label uppercase text-ink-muted">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-md p-1 text-ink-secondary hover:bg-raised hover:text-ink
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

/** Pestaña Entrenos: dos sub-vistas.
 *
 * "Historial" (por defecto) es solo la lista; "Músculos" es el body-map. Se
 * separaron porque apiladas se leían como una sola pared de datos. La
 * cola de revisión, que era el bloque de arriba, pasa a la campana: sigue
 * estando a un toque, pero no ocupa la vista principal mientras haya
 * pendientes.
 */
export function Workouts({ range }: TabProps) {
  const [view, setView] = useState<View>('historial')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [labelsOpen, setLabelsOpen] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const [showIgnored, setShowIgnored] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

  const { data, loading, error, refetch } = useApi<Workout[]>(
    `/api/workouts?from=${range.from}&to=${range.to}${showIgnored ? '&include_ignored=true' : ''}`,
  )
  const { data: daily } = useApi<DailyMetrics[]>(`/api/daily?from=${range.from}&to=${range.to}`)
  const queue = useReviewQueue(refetch)
  const { styles } = useSports()

  const sports = useMemo(() => sportsPresent(data ?? []), [data])
  const activeFilter = effectiveFilter(filter, sports)

  const shown = useMemo(
    () => (data ?? []).filter((w) => activeFilter === 'all' || w.effective_sport === activeFilter),
    [data, activeFilter],
  )
  const days = useMemo(() => groupByDay(shown), [shown])

  // La primera sesión del rango sale abierta: un panel de detalle vacío
  // esperando un clic es medio pantalla sin contestar nada.
  const selected = shown.find((w) => w.id === selectedId) ?? shown[0] ?? null

  // En móvil el detalle cae DEBAJO de la lista, así que sin esto tocar una
  // fila no parecería hacer nada.
  useEffect(() => {
    if (selectedId == null) return
    if (window.matchMedia('(min-width: 1024px)').matches) return
    detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [selectedId])

  const totalLoad = shown.reduce((sum, w) => sum + ((w.strap ?? w).train_load ?? 0), 0)

  return (
    <div className="flex flex-col gap-5 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-5">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              className={segmentClass(view === v.id)}
              aria-current={view === v.id ? 'page' : undefined}
              onClick={() => setView(v.id)}
            >
              {v.label}
            </button>
          ))}
          <span className="font-mono text-xs text-ink-muted">
            {shown.length} sesiones · {totalLoad} de carga
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setNewOpen(true)}
            aria-label="Añadir un entreno a mano"
            title="Añadir un entreno a mano"
            className="rounded-md p-2 text-ink-secondary transition-colors duration-150
                       hover:bg-raised hover:text-ink focus-visible:outline-none focus-visible:ring-2
                       focus-visible:ring-accent"
          >
            <PlusIcon className="h-5 w-5" />
          </button>

          <button
            onClick={() => setLabelsOpen(true)}
            aria-label="Etiquetas y colores"
            title="Etiquetas y colores"
            className="rounded-md p-2 text-ink-secondary transition-colors duration-150
                       hover:bg-raised hover:text-ink focus-visible:outline-none focus-visible:ring-2
                       focus-visible:ring-accent"
          >
            <TagIcon className="h-5 w-5" />
          </button>

          {/* Sin pendientes la campana NO se pinta: un icono que nunca tiene
              nada que decir es mobiliario, y la pregunta "¿qué hiciste aquí?"
              solo existe mientras haya algo sin clasificar. */}
          {queue.pending.length > 0 && (
            <button
              onClick={() => setSheetOpen(true)}
              aria-label={`Por revisar: ${queue.pending.length} entrenos sin clasificar`}
              className="relative rounded-md p-2 text-ink-secondary transition-colors duration-150
                         hover:bg-raised hover:text-ink focus-visible:outline-none focus-visible:ring-2
                         focus-visible:ring-accent"
            >
              <BellIcon className="h-5 w-5" />
              <span className="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-accent px-1 text-center font-mono text-[10px] font-semibold leading-4 text-page">
                {queue.pending.length}
              </span>
            </button>
          )}
        </div>
      </header>

      <Sheet open={sheetOpen} onClose={() => setSheetOpen(false)} title="Por revisar">
        <ReviewQueue pending={queue.pending} error={queue.error} onReview={queue.review} />
      </Sheet>

      <Sheet open={labelsOpen} onClose={() => setLabelsOpen(false)} title="Etiquetas">
        <SportLabels />
      </Sheet>

      <Sheet open={newOpen} onClose={() => setNewOpen(false)} title="Nuevo entreno">
        <NewWorkout
          onCreated={() => {
            setNewOpen(false)
            refetch()
          }}
        />
      </Sheet>

      {view === 'musculos' ? (
        <BodyMap range={range} />
      ) : (
        <AsyncState
          loading={loading && !data}
          error={error}
          isEmpty={days.length === 0}
          emptyMessage="Sin entrenos en este rango."
          errorPrefix="No se pudieron cargar los entrenos"
          onRetry={refetch}
        >
          <div className="flex flex-col gap-6">
            <div className="grid gap-8 lg:grid-cols-[380px_1fr]">
              <section className="flex flex-col gap-3 lg:max-h-[76vh] lg:overflow-y-auto lg:border-r lg:border-hairline lg:pr-6">
                {sports.length > 1 && (
                  <div className="flex flex-wrap gap-1.5">
                    {(['all', ...sports] as Filter[]).map((option) => {
                      const active = activeFilter === option
                      const color = option === 'all' ? 'var(--color-accent)' : sportColor(option, styles)
                      return (
                        <button
                          key={String(option)}
                          className={pillClass(active)}
                          style={active ? { backgroundColor: color } : undefined}
                          onClick={() => setFilter(option)}
                        >
                          {/* Punto del color del tipo también cuando la pastilla
                              está apagada: si no, el filtro no enseña el código
                              de color que sí usan los badges de la lista. */}
                          {option !== 'all' && !active && (
                            <span
                              className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle"
                              style={{ backgroundColor: color }}
                            />
                          )}
                          {option === 'all' ? 'Todos' : sportLabel(option)}
                        </button>
                      )
                    })}
                  </div>
                )}

                <div className="flex flex-col gap-4">
                  {days.map(({ day, workouts }) => (
                    <div key={day} className="flex flex-col gap-1">
                      <h3 className="text-label uppercase text-ink-muted">{formatTooltipDay(day)}</h3>
                      {workouts.map((workout) => (
                        <WorkoutRow
                          key={workout.id}
                          workout={workout}
                          selected={workout.id === selected?.id}
                          onSelect={() => setSelectedId(workout.id)}
                          styles={styles}
                        />
                      ))}
                    </div>
                  ))}
                </div>

                {/* Los descartados no se borran, se ocultan. Este interruptor es
                    el único camino de vuelta: sin él, "ignorar" era irreversible. */}
                <button
                  onClick={() => setShowIgnored((v) => !v)}
                  className="self-start text-xs text-ink-secondary underline-offset-2 hover:text-ink hover:underline
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {showIgnored ? 'Ocultar descartados' : 'Ver descartados'}
                </button>
              </section>

              <section ref={detailRef} className="flex min-w-0 flex-col gap-4">
                {selected ? (
                  <>
                    <div>
                      <div className="flex flex-wrap items-baseline gap-3">
                        <h2 className="font-serif text-2xl leading-tight">
                          {selected.effective_title ?? sportLabel(selected.effective_sport)}
                        </h2>
                        <span
                          className="rounded-sm px-1.5 py-0.5 text-label uppercase"
                          style={{
                            backgroundColor: `color-mix(in oklab, ${sportColor(selected.effective_sport, styles)} 12%, transparent)`,
                            color: sportColor(selected.effective_sport, styles),
                          }}
                        >
                          {sportLabel(selected.effective_sport)}
                        </span>
                      </div>
                      <p className="mt-1 font-mono text-xs text-ink-secondary">
                        {formatTooltipDay(dayOfTs(selected.start_ts))} · {formatClock(selected.start_ts)} –{' '}
                        {formatClock(selected.end_ts)}
                        {selected.strap && ' · Hevy + strap vinculado'}
                      </p>
                    </div>

                    <SessionStats workout={selected} />
                    <WorkoutDetail workout={selected} onEdited={refetch} />
                  </>
                ) : (
                  <p className="text-sm text-ink-secondary">Elige una sesión de la lista.</p>
                )}
              </section>
            </div>

            <div className="border-t border-hairline pt-4">
              <LoadStrip
                range={range}
                daily={daily ?? []}
                selectedDay={selected ? dayOfTs(selected.start_ts) : null}
              />
            </div>
          </div>
        </AsyncState>
      )}
    </div>
  )
}

/** La fila de cifras de la sesión. Duración, series y volumen vienen de Hevy;
 * FC, carga y efecto, del strap. Juntas son el cruce que la app oficial no
 * hace. */
function SessionStats({ workout }: { workout: Workout }) {
  const phys = workout.strap ?? workout
  const sets = workout.exercises?.reduce((n, e) => n + e.sets.length, 0) ?? null
  const volume = sessionVolume(workout.exercises)

  const stats: { label: string; value: string }[] = [
    { label: 'Duración', value: formatDuration((workout.end_ts - workout.start_ts) / 60) },
    ...(sets ? [{ label: 'Series', value: `${sets}` }] : []),
    ...(volume != null ? [{ label: 'Volumen', value: `${formatNumber(volume)} kg` }] : []),
    { label: 'FC media', value: phys.avg_hr != null ? `${phys.avg_hr}` : '–' },
    { label: 'FC máx', value: phys.max_hr != null ? `${phys.max_hr}` : '–' },
    { label: 'Carga', value: phys.train_load != null ? `${phys.train_load}` : '–' },
    { label: 'Efecto', value: phys.te != null ? phys.te.toFixed(1).replace('.', ',') : '–' },
  ]

  return (
    <div className="flex flex-wrap gap-x-8 gap-y-3 border-y border-hairline py-3">
      {stats.map((stat) => (
        <div key={stat.label}>
          <p className="text-label uppercase text-ink-muted">{stat.label}</p>
          <p className="font-mono text-xl tabular-nums">{stat.value}</p>
        </div>
      ))}
    </div>
  )
}
