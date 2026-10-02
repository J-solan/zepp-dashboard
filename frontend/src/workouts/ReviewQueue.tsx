import { useState } from 'react'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { AlertIcon, DumbbellIcon } from '../components/icons'
import { SportSuggestions } from '../components/SportSuggestions'
import { useSports } from '../hooks/useSports'
import { formatTooltipDay } from '../lib/chartFormat'
import { dayOfTs } from '../lib/date'
import { formatClock, formatDuration } from '../lib/format'
import { CLASSIFY_OPTIONS } from '../lib/workouts'
import type { ReviewBody } from '../hooks/useReviewQueue'
import type { PendingWorkout } from '../lib/types'

interface ReviewQueueProps {
  pending: PendingWorkout[]
  error: string | null
  onReview: (id: number, body: ReviewBody) => void
}

function metrics(workout: PendingWorkout): string {
  const parts = [formatDuration((workout.duration_s ?? 0) / 60)]
  if (workout.avg_hr != null) parts.push(`FC ${workout.avg_hr}`)
  if (workout.max_hr != null) parts.push(`máx ${workout.max_hr}`)
  if (workout.train_load != null) parts.push(`carga ${workout.train_load}`)
  return parts.join(' · ')
}

/** Cola "¿Qué hiciste aquí?": los workouts que el reloj auto-detectó (223) o
 * cuyo code no está en el mapa, a la espera de que el usuario diga qué fueron.
 *
 * Vive DENTRO del panel de la campana, no apilada encima de la
 * pestaña: es una pregunta que el usuario abre cuando quiere, no un bloque
 * permanente. El estado (fetch + POST + optimistic) es de `useReviewQueue`,
 * que lo comparte con el badge.
 */
export function ReviewQueue({ pending, error, onReview }: ReviewQueueProps) {
  // Tarjeta con el campo de texto libre abierto ("Otro"). Solo una a la vez:
  // clasificar es una acción puntual, no un formulario que se rellena a trozos.
  const { sports } = useSports()
  const [freeTextFor, setFreeTextFor] = useState<number | null>(null)
  const [freeText, setFreeText] = useState('')

  const classifyFreeText = (id: number) => {
    const sport = freeText.trim()
    if (!sport) return
    onReview(id, { action: 'classify', sport })
    setFreeTextFor(null)
    setFreeText('')
  }

  if (pending.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-secondary">No queda nada por revisar.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <p className="flex items-center gap-2 text-xs text-err">
          <AlertIcon className="h-4 w-4 shrink-0" />
          No se pudo guardar: {error}
        </p>
      )}

      {pending.map((workout) => (
        <Card key={workout.id} className="animate-fade-in flex flex-col gap-3 p-4">
          <div>
            <p className="text-sm font-medium text-ink">¿Qué hiciste aquí?</p>
            {/* Con la hora sola no se sabe DE QUÉ DÍA es lo que estás
                clasificando: la cola arrastra pendientes de varias fechas. */}
            <p className="mt-0.5 text-xs tabular-nums text-ink-secondary">
              {formatTooltipDay(dayOfTs(workout.start_ts))} · {formatClock(workout.start_ts)} ·{' '}
              {metrics(workout)}
            </p>
          </div>

          {workout.hevy_evidence && (
            <p className="flex items-start gap-2 rounded-lg bg-raised p-2.5 text-xs text-ink-secondary">
              <DumbbellIcon className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
              <span>
                Ese día registraste{' '}
                <span className="font-medium text-ink">
                  «{workout.hevy_evidence.title ?? 'un entreno'}»
                </span>{' '}
                en Hevy, {workout.hevy_evidence.n_sets} series
                {workout.hevy_evidence.duration_s != null &&
                  ` · ${formatDuration(workout.hevy_evidence.duration_s / 60)}`}
                .
              </span>
            </p>
          )}

          {freeTextFor === workout.id ? (
            <form
              className="flex flex-wrap gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                classifyFreeText(workout.id)
              }}
            >
              <SportSuggestions id="sugerencias-revision" sports={sports} />
              <input
                autoFocus
                list="sugerencias-revision"
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
                placeholder="¿Qué fue? (p. ej. pádel)"
                maxLength={40}
                aria-label="Tipo de entreno"
                className="min-w-40 flex-1 rounded-lg border border-hairline bg-raised px-3 py-2 text-sm
                           text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-accent"
              />
              <Button type="submit" disabled={!freeText.trim()}>
                Guardar
              </Button>
              <Button type="button" variant="ghost" onClick={() => setFreeTextFor(null)}>
                Cancelar
              </Button>
            </form>
          ) : (
            <div className="flex flex-wrap gap-2">
              {CLASSIFY_OPTIONS.map((option) => (
                <Button
                  key={option.value}
                  onClick={() => onReview(workout.id, { action: 'classify', sport: option.value })}
                >
                  {option.label}
                </Button>
              ))}
              <Button
                variant="ghost"
                onClick={() => {
                  setFreeTextFor(workout.id)
                  setFreeText('')
                }}
              >
                Otro…
              </Button>
              <Button variant="ghost" onClick={() => onReview(workout.id, { action: 'ignore' })}>
                Ignorar
              </Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
