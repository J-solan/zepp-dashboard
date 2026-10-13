import { useState } from 'react'
import { Button } from '../components/Button'
import { useApi } from '../hooks/useApi'
import { useWorkoutEdit } from '../hooks/useWorkoutEdit'
import { dayOfTs } from '../lib/date'
import { formatClock, formatDuration } from '../lib/format'
import { sportLabel } from '../lib/workouts'
import type { Workout } from '../lib/types'

/** Sesiones de la pulsera de ese día. Componente aparte para que el GET solo
 * salga al abrir la lista. Las descartadas van incluidas: son justo el caso que
 * el vínculo automático no empareja. Las ya vinculadas a un entreno de Hevy no
 * salen (`/api/workouts` las absorbe), y no se podrían elegir de todas formas. */
function Candidates({ day, disabled, onPick }: {
  day: string
  disabled: boolean
  onPick: (strapId: number) => void
}) {
  const { data, error } = useApi<Workout[]>(`/api/workouts?from=${day}&to=${day}&include_ignored=true`)
  const sessions = (data ?? []).filter((w) => w.source === 'zepp')

  if (error) return <p className="text-xs text-err">No se pudieron cargar las sesiones: {error}</p>
  if (!data) return <p className="text-xs text-ink-muted">Cargando sesiones…</p>
  if (sessions.length === 0) {
    return <p className="text-xs text-ink-secondary">Ese día no hay sesiones de la pulsera libres.</p>
  }
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs text-ink-muted">Elige la sesión. Al vincularla pasa a ser de fuerza.</p>
      {sessions.map((s) => (
        <Button
          key={s.id}
          variant="ghost"
          disabled={disabled}
          onClick={() => onPick(s.id)}
          className="justify-start px-3 py-1.5 text-xs tabular-nums"
        >
          {formatClock(s.start_ts)} · {formatDuration((s.duration_s ?? 0) / 60)} · {sportLabel(s.effective_sport)}
          {s.review_status === 'ignored' && <span className="text-ink-muted">· descartada</span>}
        </Button>
      ))}
    </div>
  )
}

/** Vínculo a mano de un entreno de Hevy con la pulsera.
 *
 * El automático solo empareja si ese día hay exactamente UNA sesión de fuerza
 * en la pulsera; esto cubre el resto (la sesión se descartó, quedó como otra
 * cosa, o hay varias). El backend hace fuerza la sesión elegida para que el
 * siguiente import de Hevy la vuelva a encontrar. */
export function StrapLink({ workout }: { workout: Workout }) {
  const [open, setOpen] = useState(false)
  const { saving, error, link } = useWorkoutEdit(workout.id)

  const pick = async (strapId: number | null) => {
    if (await link(strapId)) setOpen(false)
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" onClick={() => setOpen((v) => !v)} className="px-3 py-1.5 text-xs">
          {workout.strap ? 'Cambiar sesión de la pulsera' : 'Vincular con la pulsera'}
        </Button>
        {workout.strap && (
          <Button variant="ghost" onClick={() => pick(null)} disabled={saving} className="px-3 py-1.5 text-xs">
            Desvincular
          </Button>
        )}
      </div>
      {open && <Candidates day={dayOfTs(workout.start_ts)} disabled={saving} onPick={pick} />}
      {error && <p className="text-xs text-err">No se pudo guardar: {error}</p>}
    </div>
  )
}
