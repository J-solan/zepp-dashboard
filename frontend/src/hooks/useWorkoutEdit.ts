import { useCallback, useState } from 'react'
import { clearApiCache } from './useApi'
import { fetchJson } from '../lib/api'
import type { Workout } from '../lib/types'

/** Campos editables. Ausente = no tocar; `null` = borrar. Esa distinción la
 * respeta el backend (`PATCH /api/workouts/{id}`) y es lo que permite vaciar
 * una nota sin pisar el título. */
export interface WorkoutPatch {
  user_title?: string | null
  notes?: string | null
  user_sport?: string | null
}

export interface WorkoutEdit {
  saving: boolean
  error: string | null
  save: (patch: WorkoutPatch) => Promise<boolean>
  /** Deshace un descarte: vuelve a la cola. */
  restore: () => Promise<boolean>
  /** Solo entrenos manuales; el backend responde 409 en los demás. */
  remove: () => Promise<boolean>
}

/** Edición de un entreno contra `PATCH /api/workouts/{id}`.
 *
 * No hace optimistic update, al contrario que `useReviewQueue`: allí la acción
 * retira una fila de una lista y el resultado se ve solo, aquí el usuario está
 * mirando el campo que acaba de escribir y un rollback silencioso sería peor
 * que esperar. Al guardar se invalida la caché para que la lista se repinte con
 * el título nuevo.
 */
export function useWorkoutEdit(workoutId: number, onSaved: () => void): WorkoutEdit {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const request = useCallback(
    async (path: string, init: RequestInit) => {
      setSaving(true)
      setError(null)
      try {
        await fetchJson<Workout>(path, init)
        clearApiCache()
        onSaved()
        return true
      } catch (err) {
        setError((err as Error).message)
        return false
      } finally {
        setSaving(false)
      }
    },
    [onSaved],
  )

  const save = useCallback(
    (patch: WorkoutPatch) =>
      request(`/api/workouts/${workoutId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      }),
    [request, workoutId],
  )

  const restore = useCallback(
    () =>
      request(`/api/workouts/${workoutId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'restore' }),
      }),
    [request, workoutId],
  )

  const remove = useCallback(
    () => request(`/api/workouts/${workoutId}`, { method: 'DELETE' }),
    [request, workoutId],
  )

  return { saving, error, save, restore, remove }
}
