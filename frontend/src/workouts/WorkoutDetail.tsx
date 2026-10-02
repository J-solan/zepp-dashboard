import { useMemo } from 'react'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { dayOfTs } from '../lib/date'
import { METRIC, SPORT } from '../lib/palette'
import { muscleLabel, zoneBands } from '../lib/workouts'
import { formatDuration } from '../lib/format'
import { WorkoutEditor } from './WorkoutEditor'
import type { Workout, WorkoutExercise, WorkoutMuscle } from '../lib/types'

/** Chips de músculo teñidos por intensidad: el principal (1.0) tira del color
 * de fuerza y los secundarios se van apagando. Es la información que la app
 * oficial no puede dar — el strap adivina el patrón de muñeca, el músculo sale
 * del mapa curado de Hevy. */
function Muscles({ muscles }: { muscles: WorkoutMuscle[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {muscles.map((m) => (
        <span
          key={m.muscle}
          className="rounded-full border border-hairline px-2 py-0.5 text-xs text-ink"
          style={{
            backgroundColor: `color-mix(in oklab, ${SPORT.fuerza} ${Math.round(m.intensity * 30)}%, transparent)`,
          }}
        >
          {muscleLabel(m.muscle)} <span className="text-ink-muted">{Math.round(m.intensity * 100)}%</span>
        </span>
      ))}
    </div>
  )
}

function SetsTable({ exercise }: { exercise: WorkoutExercise }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-ink">{exercise.exercise}</p>
        {exercise.muscle_group && <p className="text-xs text-ink-muted">{exercise.muscle_group}</p>}
      </div>
      <table className="mt-1 w-full text-sm tabular-nums">
        <tbody>
          {exercise.sets.map((set, i) => {
            const warmup = set.set_type === 'warmup'
            return (
              <tr key={i} className={warmup ? 'text-ink-muted' : 'text-ink-secondary'}>
                <td className="w-8 py-0.5">
                  {warmup ? (
                    <span title="Calentamiento" className="text-label uppercase">
                      cal
                    </span>
                  ) : (
                    (set.set_index ?? i) + 1
                  )}
                </td>
                <td className="py-0.5">
                  <span className={warmup ? '' : 'font-medium text-ink'}>
                    {set.weight_kg ?? '–'} kg
                  </span>{' '}
                  × {set.reps ?? '–'}
                </td>
                <td className="py-0.5 text-right text-xs">{set.rpe != null ? `RPE ${set.rpe}` : ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function HrZones({ zones }: { zones: Workout['hr_zones'] }) {
  const bands = useMemo(() => zoneBands(zones), [zones])
  if (bands.length === 0) return null
  return (
    <div className="flex flex-col gap-2">
      <p className="text-label uppercase text-ink-muted">Zonas de FC</p>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        {bands.map((band) => (
          <span
            key={band.threshold}
            style={{ width: `${band.share * 100}%`, backgroundColor: band.color }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {bands.map((band) => (
          <span key={band.threshold} className="flex items-center gap-1.5 text-xs text-ink-secondary">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: band.color }}
            />
            {band.label} bpm
            <span className="tabular-nums text-ink">{formatDuration(band.seconds / 60)}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/** Detalle de un entreno.
 *
 * Fuerza = lo de Hevy (series por ejercicio, músculos) MÁS el overlay del
 * strap; vóley, auto-detectados y 223 reclasificados = solo el strap. Es la
 * misma pieza para los dos casos porque el bloque fisiológico es idéntico:
 * cambia si hay o no tabla de series encima. */
export function WorkoutDetail({ workout, onEdited }: { workout: Workout; onEdited: () => void }) {
  // El lado fisiológico vive en el workout del strap cuando este viene de Hevy.
  const phys = workout.strap ?? workout
  const overlay = useMemo(
    () => (workout.hr_overlay ?? []).map((p) => ({ ts: p.ts, value: p.bpm })),
    [workout.hr_overlay],
  )
  const bounds = useMemo<[number, number]>(
    () => [workout.start_ts, workout.end_ts],
    [workout.start_ts, workout.end_ts],
  )

  return (
    <div className="flex flex-col gap-4">
      {workout.exercises && workout.exercises.length > 0 && (
        <div className="flex flex-col gap-3">
          {workout.exercises.map((exercise, i) => (
            <SetsTable key={`${exercise.exercise}-${i}`} exercise={exercise} />
          ))}
        </div>
      )}

      {workout.muscles && workout.muscles.length > 0 && <Muscles muscles={workout.muscles} />}

      <HrZones zones={phys.hr_zones} />

      {overlay.length > 0 && (
        <TimeSeriesChart
          data={overlay}
          series={[{ dataKey: 'value', color: METRIC.hr }]}
          range={{ from: dayOfTs(workout.start_ts), to: dayOfTs(workout.start_ts) }}
          bounds={bounds}
          unit="bpm"
          height="sm"
        />
      )}

      <WorkoutEditor workout={workout} onSaved={onEdited} />
    </div>
  )
}
