import { formatClock, formatDuration } from '../lib/format'
import { sportColor, sportLabel } from '../lib/workouts'
import type { SportStyles } from '../lib/workouts'
import type { Workout } from '../lib/types'

interface WorkoutRowProps {
  workout: Workout
  selected: boolean
  onSelect: () => void
  styles?: SportStyles
}

function summary(workout: Workout): string {
  const parts: string[] = []
  if (workout.duration_s != null) parts.push(formatDuration(workout.duration_s / 60))
  const sets = workout.exercises?.reduce((n, e) => n + e.sets.length, 0)
  if (sets) parts.push(`${sets} series`)
  const phys = workout.strap ?? workout
  if (phys.avg_hr != null) parts.push(`FC ${phys.avg_hr}`)
  if (phys.train_load != null) parts.push(`carga ${phys.train_load}`)
  return parts.join(' · ')
}

/** Fila de la lista: hora, tipo y lo que se lee de un vistazo.
 *
 * Ya no despliega nada. El detalle vive al lado (o debajo, en móvil) y se
 * sustituye al elegir otra fila: comparar dos sesiones era antes abrir, leer,
 * cerrar y abrir la siguiente de memoria. */
export function WorkoutRow({ workout, selected, onSelect, styles }: WorkoutRowProps) {
  const color = sportColor(workout.effective_sport, styles)
  // Marcador sutil de "esto sigue sin clasificar": el badge va con borde
  // discontinuo. La pregunta completa está en la campana, aquí solo se
  // señala que la etiqueta es provisional.
  const unreviewed = workout.review_status === 'pending'

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      // Un descartado se ve APAGADO, no oculto: aparece solo al pedir "ver
      // descartados", y ahí tiene que distinguirse de un vistazo de los vivos.
      className={
        'flex w-full items-center gap-3 border-l-[3px] py-2 pl-2 pr-1 text-left transition-colors duration-150 ' +
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ' +
        (workout.review_status === 'ignored' ? 'opacity-50 ' : '') +
        (selected ? 'border-accent bg-raised' : 'border-transparent hover:bg-raised/50')
      }
    >
      <span className="w-11 shrink-0 font-mono text-sm tabular-nums">{formatClock(workout.start_ts)}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span
            className={`rounded-sm px-1.5 py-0.5 text-label uppercase ${unreviewed ? 'border border-dashed' : ''}`}
            style={{
              // 12% y no más: el texto del badge es ESE mismo color a 10px, y
              // con el fondo más teñido la pareja se queda por debajo de 4.5:1.
              backgroundColor: `color-mix(in oklab, ${color} 12%, transparent)`,
              color,
              borderColor: unreviewed ? color : undefined,
            }}
          >
            {sportLabel(workout.effective_sport)}
          </span>
          {/* La detección automática es un hecho del ORIGEN, no una categoría:
              sigue siendo cierta después de reclasificarlo. */}
          {workout.auto_recognized && (
            <span
              title="Detectado automáticamente por el reloj"
              className="shrink-0 rounded-sm bg-raised px-1 py-0.5 text-label uppercase text-ink-muted"
            >
              auto
            </span>
          )}
          {workout.effective_title && (
            <span className="truncate text-xs text-ink-secondary">{workout.effective_title}</span>
          )}
        </span>
        <span className="mt-0.5 block truncate font-mono text-xs tabular-nums text-ink-secondary">
          {summary(workout)}
        </span>
      </span>
    </button>
  )
}
