import { useMemo, useState } from 'react'
import { AsyncState } from '../components/AsyncState'
import { useApi } from '../hooks/useApi'
import { BODY_FILL, muscleFill } from '../lib/muscleScale'
import { formatNumber } from '../lib/format'
import { muscleLabel } from '../lib/workouts'
import { BACK, FRONT, NEUTRAL_BACK, NEUTRAL_FRONT, VIEW_BOX_BACK, VIEW_BOX_FRONT } from './bodyShapes'
import type { TabProps } from '../App'
import type { MuscleVolume, MuscleVolumes } from '../lib/types'

// La figura (silueta y paths de cada músculo) vive en `bodyShapes.ts`, que es
// solo datos: las coordenadas se iteran sin tocar este componente.

const kg = (volume: number) => `${formatNumber(volume)} kg`

// Trazo de la lámina, constante en toda la figura. Es lo que dibuja la
// anatomía cuando no hay carga: sobre papel basta un gris cálido — con la
// tinta a plena fuerza la figura se leía como un dibujo a rotulador.
const LINE = 'color-mix(in oklab, var(--color-ink) 30%, transparent)'

interface BodyProps {
  view: string
  shapes: Record<string, string[]>
  /** Piezas que no son músculo (cabeza, cuello, rodillas, manos, pies). */
  neutral: string[]
  /** Lienzo ajustado a ESA vista: con uno común, la posterior salía más larga
   * que la frontal y las dos figuras no quedaban a la misma altura. */
  viewBox: string
  volumes: Map<string, MuscleVolume>
  max: number
  picked: string | null
  onPick: (muscle: string) => void
  /** Visibilidad: en móvil solo se pinta la vista elegida. */
  className?: string
}

function Paths({ paths }: { paths: string[] }) {
  return (
    <>
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </>
  )
}

function Body({ view, shapes, neutral, viewBox, volumes, max, picked, onPick, className = '' }: BodyProps) {
  return (
    <figure className={`m-0 min-w-0 flex-1 flex-col items-center gap-1 ${className}`}>
      {/* Las dos vistas se igualan por ALTURA, no por ancho: el set de origen
          dibuja la espalda algo más larga que el frente, así que a igual ancho
          una figura salía más alta que la otra. */}
      <div className="flex h-[26rem] w-full items-center justify-center sm:h-[34rem]">
        <svg viewBox={viewBox} className="h-full w-auto max-w-full" aria-label={`Vista ${view}`}>
          {Object.entries(shapes).map(([muscle, paths]) => {
            const volume = volumes.get(muscle)?.volume ?? 0
            const sets = volumes.get(muscle)?.sets ?? 0
            const active = picked === muscle
            return (
              <g
                key={muscle}
                role="button"
                tabIndex={0}
                aria-label={`${muscleLabel(muscle)}: ${kg(volume)}, ${sets} series`}
                className="cursor-pointer outline-none transition-[fill,stroke] duration-300"
                fill={muscleFill(volume, max)}
                // El contorno NO depende de la carga: es el que define el
                // músculo cuando no tiene ninguna.
                stroke={active ? 'var(--color-ink)' : LINE}
                strokeWidth={active ? 1.7 : 0.85}
                onMouseEnter={() => onPick(muscle)}
                onFocus={() => onPick(muscle)}
                onClick={() => onPick(muscle)}
              >
                <title>{`${muscleLabel(muscle)} · ${kg(volume)}`}</title>
                <Paths paths={paths} />
              </g>
            )
          })}

          {/* NO hay silueta de fondo: el cuerpo son los músculos, que teselan la
              figura y con sus bordes exteriores hacen el contorno. Aquí solo van
              las piezas que no son músculo (cabeza, cuello, manos y pies), con el
              mismo trazo y relleno neutro. Se pintan LAS ÚLTIMAS: el trapecio del
              set sube por encima del cuello y, debajo, se comía la cabeza. */}
          <g fill={BODY_FILL} stroke={LINE} strokeWidth="0.85">
            <Paths paths={neutral} />
          </g>
        </svg>
      </div>
      <figcaption className="text-label text-center uppercase text-ink-muted">{view}</figcaption>
    </figure>
  )
}

/** Mapa de volumen por músculo sobre un cuerpo humano.
 *
 * Es lo que ninguna app oficial puede pintar: el músculo sale del mapa curado
 * de Hevy (`muscle_map.toml`), no del patrón de muñeca que el strap falla el
 * ~80% de las veces. El color se normaliza contra el músculo MÁS trabajado del
 * rango, así que responde "qué he trabajado más", no "cuánto peso he movido".
 */
export function BodyMap({ range }: TabProps) {
  // En móvil no caben dos figuras de 8 cabezas sin quedarse en miniatura: se
  // enseña una y se conmuta. En pantalla ancha caben las dos y verlas juntas
  // es justo la gracia (equilibrio empuje/tirón de un vistazo).
  const [view, setView] = useState<'front' | 'back'>('front')
  const [picked, setPicked] = useState<string | null>(null)

  const { data, loading, error, refetch } = useApi<MuscleVolumes>(
    `/api/muscles/volume?from=${range.from}&to=${range.to}`,
  )

  const volumes = useMemo(() => new Map((data?.muscles ?? []).map((m) => [m.muscle, m])), [data])
  const ranking = useMemo(
    () => [...(data?.muscles ?? [])].sort((a, b) => b.volume - a.volume),
    [data],
  )
  const max = Math.max(0, ...ranking.map((m) => m.volume))

  // Un músculo sin volumen en el rango se puede seleccionar igual: contestar
  // "esta semana, cero" es información, no un hueco.
  const active: MuscleVolume | null = picked
    ? (volumes.get(picked) ?? { muscle: picked, volume: 0, sets: 0, top_exercises: [] })
    : null

  // Regiones de la figura que no recibieron nada, y músculos del mapa del
  // usuario que no tienen forma en la figura: los dos casos se dicen, en vez
  // de desaparecer sin avisar.
  const untouched = useMemo(
    () => [...new Set([...Object.keys(FRONT), ...Object.keys(BACK)])].filter((m) => !(volumes.get(m)?.volume ?? 0)),
    [volumes],
  )
  const orphans = ranking.filter((m) => !(m.muscle in FRONT || m.muscle in BACK))

  return (
    <AsyncState
      loading={loading && !data}
      error={error}
      // El vacío NO se delega: con el rango sin fuerza el mapa se sigue
      // pintando en neutro (es la respuesta: no tocaste nada).
      isEmpty={false}
      emptyMessage=""
      errorPrefix="No se pudo cargar el volumen por músculo"
      onRetry={refetch}
    >
      <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex justify-center gap-1 sm:hidden">
            {(
              [
                ['front', 'Frontal'],
                ['back', 'Posterior'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                className={
                  'rounded-sm px-3 py-1 text-sm transition-colors duration-150 ' +
                  (view === id ? 'bg-ink text-page' : 'text-ink-secondary hover:text-ink')
                }
                aria-pressed={view === id}
                onClick={() => setView(id)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex justify-center gap-6">
            <Body
              view="Frontal"
              shapes={FRONT}
              neutral={NEUTRAL_FRONT}
              viewBox={VIEW_BOX_FRONT}
              volumes={volumes}
              max={max}
              picked={picked}
              onPick={setPicked}
              className={view === 'front' ? 'flex' : 'hidden sm:flex'}
            />
            <Body
              view="Posterior"
              shapes={BACK}
              neutral={NEUTRAL_BACK}
              viewBox={VIEW_BOX_BACK}
              volumes={volumes}
              max={max}
              picked={picked}
              onPick={setPicked}
              className={view === 'back' ? 'flex' : 'hidden sm:flex'}
            />
          </div>

          <div className="flex items-center gap-2 border-t border-hairline pt-3 font-mono text-[11px] tabular-nums text-ink-muted">
            <span>0</span>
            <span
              className="h-2 flex-1"
              style={{
                background: `linear-gradient(to right, ${muscleFill(0, 1)}, ${muscleFill(0.5, 1)}, ${muscleFill(1, 1)})`,
              }}
            />
            <span>{max > 0 ? kg(max) : 'sin fuerza en el rango'}</span>
          </div>
        </div>

        <div className="flex flex-col gap-5">
          <div>
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-label uppercase text-ink-muted">Volumen por músculo</p>
              {data && data.total_volume > 0 && (
                <span className="font-mono text-xs text-ink-secondary">{kg(data.total_volume)} movidos</span>
              )}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-secondary">
              Peso × repeticiones × cuánto entra cada músculo. Es comparable entre músculos, así que contesta
              «qué he trabajado más», no «cuánto peso he movido».
            </p>

            {ranking.length === 0 ? (
              <p className="mt-3 text-sm text-ink-secondary">Sin entrenos de fuerza en este rango.</p>
            ) : (
              <div className="mt-3 flex flex-col gap-1.5">
                {ranking.map((m) => (
                  <button
                    key={m.muscle}
                    onClick={() => setPicked(m.muscle)}
                    onMouseEnter={() => setPicked(m.muscle)}
                    className="flex items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <span
                      className={`w-20 shrink-0 truncate text-xs ${picked === m.muscle ? 'text-ink' : 'text-ink-secondary'}`}
                    >
                      {muscleLabel(m.muscle)}
                    </span>
                    <span
                      className="h-2.5"
                      style={{
                        width: `${Math.max((m.volume / (max || 1)) * 190, 2)}px`,
                        backgroundColor: muscleFill(m.volume, max),
                        outline: picked === m.muscle ? '1px solid var(--color-ink)' : undefined,
                      }}
                    />
                    <span className="ml-auto font-mono text-[11px] tabular-nums text-ink-muted">
                      {formatNumber(m.volume)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {active && (
            <div className="animate-fade-in border-t border-ink pt-3">
              <div className="flex items-baseline justify-between gap-2">
                <p className="font-serif text-xl leading-tight">{muscleLabel(active.muscle)}</p>
                <p className="font-mono text-xs text-ink-secondary">
                  {kg(active.volume)} · {active.sets} series
                </p>
              </div>
              {active.top_exercises.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1">
                  {active.top_exercises.map((exercise) => (
                    <li key={exercise.exercise} className="flex items-baseline justify-between gap-3 text-xs">
                      <span className="truncate text-ink-secondary">{exercise.exercise}</span>
                      <span className="shrink-0 font-mono tabular-nums text-ink-muted">{kg(exercise.volume)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-ink-muted">Sin series en este rango.</p>
              )}
            </div>
          )}

          {!active && ranking.length > 0 && (
            <p className="text-xs text-ink-muted">
              Toca un músculo (en la figura o en la lista) para ver de qué ejercicios sale su volumen.
            </p>
          )}

          {untouched.length > 0 && ranking.length > 0 && (
            <div className="border-t border-hairline pt-3">
              <p className="text-label uppercase text-ink-muted">Sin nada en este rango</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-secondary">
                {untouched.map((m) => muscleLabel(m)).join(' · ')}
              </p>
            </div>
          )}

          {orphans.length > 0 && (
            <p className="text-xs text-ink-muted">
              Fuera de la figura: {orphans.map((m) => `${muscleLabel(m.muscle)} (${kg(m.volume)})`).join(' · ')}
            </p>
          )}
        </div>
      </div>
    </AsyncState>
  )
}
