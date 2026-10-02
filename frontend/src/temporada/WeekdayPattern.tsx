import { quantiles } from '../lib/baseline'

const WEEKDAYS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']

interface WeekdayPatternProps {
  /** Mediana por día de la semana, de lunes a domingo. */
  medians: (number | null)[]
  color: string
  label: string
  format: (value: number) => string
}

/** El patrón que no se ve día a día: cómo va cada día de la semana comparado
 * con los demás. El peor va destacado, porque es el que da pie a cambiar algo. */
export function WeekdayPattern({ medians, color, label, format }: WeekdayPatternProps) {
  const values = medians.filter((v): v is number => v != null)
  if (values.length < 3) {
    return <p className="text-sm text-ink-secondary">Aún no hay semanas suficientes para ver un patrón.</p>
  }

  const band = quantiles(values)!
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const worstIndex = medians.indexOf(lo)
  const bestIndex = medians.indexOf(hi)
  // Escala con suelo por debajo del mínimo: arrancando en cero, siete barras
  // de valores parecidos salen iguales y el patrón se pierde.
  const floor = lo - (hi - lo || 1) * 0.6

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-label uppercase text-ink-muted">{label} por día de la semana</p>
        <p className="font-mono text-[11px] text-ink-muted">mediana {format(band.median)}</p>
      </div>

      <div className="flex h-40 items-end gap-2">
        {medians.map((value, i) => (
          <div key={WEEKDAYS[i]} className="flex h-full flex-1 flex-col justify-end gap-1.5">
            <span className="text-center font-mono text-[11px] tabular-nums text-ink-secondary">
              {value != null ? format(value) : '–'}
            </span>
            <div
              className="w-full"
              style={{
                height: value != null ? `${((value - floor) / (hi - floor)) * 100}%` : '2px',
                backgroundColor: value == null ? 'var(--color-grid)' : i === worstIndex ? 'var(--color-accent)' : color,
              }}
            />
            <span
              className={
                'text-center text-[11px] ' +
                (i === worstIndex ? 'text-accent' : i === bestIndex ? 'text-ink' : 'text-ink-muted')
              }
            >
              {WEEKDAYS[i]}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
