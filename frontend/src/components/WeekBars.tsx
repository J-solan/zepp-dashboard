import { useState } from 'react'
import type { DayValue } from '../lib/days'

const DAY_FMT = new Intl.DateTimeFormat('es-ES', { weekday: 'short', day: 'numeric', timeZone: 'UTC' })

/** "mié 30" de un día ISO. Se formatea en UTC a propósito: el string YA es el
 * día local, así que reinterpretarlo en otra zona solo puede restarle un día. */
function formatDay(day: string): string {
  const [year, month, d] = day.split('-').map(Number)
  return DAY_FMT.format(new Date(Date.UTC(year, month - 1, d)))
}

interface WeekBarsProps {
  data: DayValue[]
  color: string
  /** Formato del valor en la línea de lectura (p.ej. miles con separador). */
  format: (value: number) => string
  /** Meta diaria opcional: dibuja su línea y atenúa los días que no llegan. */
  goal?: number
}

/** Barras de los últimos días con lectura al señalar.
 *
 * Mismo trato que el hipnograma: la línea de arriba tiene ALTURA FIJA y dos
 * estados (media de la semana en reposo, el día señalado al apuntar), y las
 * barras viven en una pista de altura fija con la altura en %. Nada crece ni
 * aparece al pasar por encima, así que la tarjeta no da saltos.
 *
 * `onPointerEnter` + `onPointerDown` para que valga con ratón y con el dedo; la
 * columna entera es la zona de captura, no la barra (con 4 px de ancho no se
 * acierta con el dedo).
 */
export function WeekBars({ data, color, format, goal }: WeekBarsProps) {
  const [active, setActive] = useState<number | null>(null)

  const values = data.filter((d): d is DayValue & { value: number } => d.value != null)
  if (values.length === 0) {
    return <p className="py-3 text-xs text-ink-muted">sin datos de los últimos {data.length} días</p>
  }

  // La escala incluye la meta: si no, un día flojo llenaría la pista y parecería
  // que se llegó. Los días sin dato no puntúan en la media.
  const max = Math.max(...values.map((d) => d.value), goal ?? 0)
  const avg = values.reduce((sum, d) => sum + d.value, 0) / values.length
  const reached = goal != null ? values.filter((d) => d.value >= goal).length : 0
  const current = active != null ? data[active] : null

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex h-4 items-center gap-2 overflow-hidden text-[11px] leading-4 tabular-nums">
        {current ? (
          <span className="truncate">
            <span className="text-ink-secondary">{formatDay(current.day)}</span>{' '}
            <span style={{ color: current.value != null ? color : undefined }}>
              {current.value != null ? format(current.value) : 'sin dato'}
            </span>
            {goal != null && current.value != null && (
              <span className="text-ink-muted"> · {current.value >= goal ? 'meta ✓' : 'sin meta'}</span>
            )}
          </span>
        ) : (
          <span className="truncate text-ink-muted">
            media {data.length} d {format(avg)}
            {goal != null && ` · ${reached}/${values.length} con meta`}
          </span>
        )}
      </div>

      <div className="relative flex h-9 items-end gap-1" onPointerLeave={() => setActive(null)}>
        {goal != null && goal <= max && (
          <div
            className="pointer-events-none absolute inset-x-0 border-t border-dashed border-ink-muted/50"
            style={{ bottom: `${(goal / max) * 100}%` }}
          />
        )}
        {data.map((d, i) => {
          const dimmed = active != null && active !== i
          const belowGoal = goal != null && (d.value ?? 0) < goal
          return (
            <div
              key={d.day}
              className="flex h-full flex-1 cursor-pointer flex-col justify-end"
              title={`${formatDay(d.day)} · ${d.value != null ? format(d.value) : 'sin dato'}`}
              onPointerEnter={() => setActive(i)}
              onPointerDown={() => setActive(i)}
            >
              <div
                className="rounded-sm transition-opacity duration-150"
                style={{
                  // Suelo del 6 %: un día casi a cero debe seguir viéndose como
                  // barra (hubo dato) y no como hueco.
                  height: d.value != null ? `${Math.max((d.value / max) * 100, 6)}%` : '2px',
                  backgroundColor: d.value != null ? color : 'var(--color-grid)',
                  opacity: dimmed ? 0.3 : belowGoal ? 0.55 : 1,
                }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
