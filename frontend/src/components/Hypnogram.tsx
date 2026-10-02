import { useMemo, useState } from 'react'
import { formatClock, formatDuration } from '../lib/format'
import { STAGE_COLORS, STAGE_LABELS } from '../lib/sleep'
import type { SleepSession } from '../lib/types'

// Orden de fila top -> bottom, como un hipnograma clínico: despierto arriba,
// profundo abajo.
const ROW_ORDER = [7, 8, 4, 5]
const ROW_HEIGHT = 40 / ROW_ORDER.length

function rowIndex(stage: number): number {
  const i = ROW_ORDER.indexOf(stage)
  return i === -1 ? 1 : i
}

interface HypnogramProps {
  session: SleepSession
}

/** Hipnograma de una noche, interactivo.
 *
 * La línea de arriba tiene altura fija y dos estados: en reposo enseña el
 * reparto de la noche (cuánto de cada fase) y al señalar un tramo lo cambia por
 * ese tramo concreto. Fija a propósito: si apareciera y desapareciera, la
 * tarjeta daría un salto cada vez que pasas el ratón por encima.
 */
export function Hypnogram({ session }: HypnogramProps) {
  const [active, setActive] = useState<number | null>(null)
  const total = session.end_ts - session.start_ts

  // Minutos por fase de ESTA sesión: se derivan de los tramos y no de los
  // campos del resumen para que lo que se lee cuadre siempre con lo que se ve.
  const totals = useMemo(() => {
    const acc = new Map<number, number>()
    for (const s of session.stages) acc.set(s.stage, (acc.get(s.stage) ?? 0) + (s.end_ts - s.start_ts))
    return acc
  }, [session])

  if (total <= 0) return null

  const current = active != null ? session.stages[active] : null

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex h-4 items-center gap-3 overflow-hidden text-[11px] leading-4 tabular-nums">
        {current ? (
          <span className="truncate">
            <span style={{ color: STAGE_COLORS[current.stage] }}>
              {STAGE_LABELS[current.stage] ?? `Fase ${current.stage}`}
            </span>
            <span className="text-ink-secondary">
              {' '}
              {formatClock(current.start_ts)}–{formatClock(current.end_ts)} ·{' '}
              {formatDuration((current.end_ts - current.start_ts) / 60)}
            </span>
            <span className="text-ink-muted">
              {' '}
              · total {formatDuration((totals.get(current.stage) ?? 0) / 60)}
            </span>
          </span>
        ) : (
          ROW_ORDER.filter((stage) => totals.has(stage)).map((stage) => (
            <span key={stage} className="flex shrink-0 items-center gap-1 text-ink-muted">
              <span
                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: STAGE_COLORS[stage] }}
              />
              {formatDuration((totals.get(stage) ?? 0) / 60)}
            </span>
          ))
        )}
      </div>

      <div className="flex gap-2">
        <div className="flex h-24 w-14 shrink-0 flex-col justify-between py-1 text-right">
          {ROW_ORDER.map((stage) => (
            <span
              key={stage}
              className="text-[10px] leading-none transition-colors duration-150"
              style={{ color: current?.stage === stage ? STAGE_COLORS[stage] : 'var(--color-ink-muted)' }}
            >
              {STAGE_LABELS[stage] ?? '—'}
            </span>
          ))}
        </div>
        <svg
          viewBox="0 0 100 40"
          preserveAspectRatio="none"
          className="h-24 w-full rounded-md bg-page/50"
          onPointerLeave={() => setActive(null)}
        >
          {session.stages.map((stage, i) => {
            const left = ((stage.start_ts - session.start_ts) / total) * 100
            const width = ((stage.end_ts - stage.start_ts) / total) * 100
            const dimmed = current != null && current.stage !== stage.stage
            return (
              <rect
                key={i}
                x={left}
                y={rowIndex(stage.stage) * ROW_HEIGHT + 1}
                width={Math.max(width, 0.15)}
                height={ROW_HEIGHT - 2}
                rx={0.8}
                fill={STAGE_COLORS[stage.stage] ?? 'var(--color-ink-muted)'}
                opacity={dimmed ? 0.3 : 1}
                className="transition-opacity duration-150"
              />
            )
          })}

          {/* Zonas de captura a toda la altura, una por tramo: los tramos son
              consecutivos en el tiempo, así que no se solapan, y así se acierta
              con el dedo sin tener que dar en una barra de 3 mm. */}
          {session.stages.map((stage, i) => {
            const left = ((stage.start_ts - session.start_ts) / total) * 100
            const width = ((stage.end_ts - stage.start_ts) / total) * 100
            return (
              <rect
                key={`hit-${i}`}
                x={left}
                y={0}
                width={Math.max(width, 0.6)}
                height={40}
                fill="transparent"
                className="cursor-pointer"
                onPointerEnter={() => setActive(i)}
                onPointerDown={() => setActive(i)}
              >
                <title>
                  {`${STAGE_LABELS[stage.stage] ?? `Fase ${stage.stage}`} · ${formatClock(stage.start_ts)}–${formatClock(stage.end_ts)}`}
                </title>
              </rect>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
