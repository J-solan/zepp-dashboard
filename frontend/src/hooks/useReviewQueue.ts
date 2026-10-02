import { useCallback, useState } from 'react'
import { clearApiCache, useApi } from './useApi'
import { fetchJson } from '../lib/api'
import type { PendingWorkout } from '../lib/types'

export interface ReviewBody {
  action: 'classify' | 'ignore'
  /** Tipo asignado. Texto libre: 'fuerza'/'voley_playa' son atajos, pero el
   * usuario puede escribir lo que hizo ("pádel") y el backend lo guarda tal
   * cual en `user_sport`. */
  sport?: string
}

export interface ReviewQueue {
  pending: PendingWorkout[]
  error: string | null
  review: (id: number, body: ReviewBody) => Promise<void>
}

/** Cola de revisión (los 223 sin clasificar) como estado compartido.
 *
 * Vive en un hook y no dentro de `ReviewQueue` porque hay DOS
 * consumidores del mismo dato: el badge de la campana en la cabecera y el
 * panel que se abre al pulsarla. Con un `useApi` en cada uno, clasificar
 * dejaría el badge desfasado hasta el siguiente refetch.
 */
export function useReviewQueue(onResolved: () => void): ReviewQueue {
  const { data, refetch } = useApi<PendingWorkout[]>('/api/workouts/pending')
  // Ids ya resueltos en esta pantalla: se retiran de la lista antes de que
  // conteste el servidor (optimistic) y vuelven si el POST falla.
  const [resolved, setResolved] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)

  const review = useCallback(
    async (id: number, body: ReviewBody) => {
      setResolved((ids) => [...ids, id])
      setError(null)
      try {
        await fetchJson(`/api/workouts/${id}/review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        clearApiCache()
        refetch()
        onResolved()
      } catch (err) {
        setResolved((ids) => ids.filter((x) => x !== id))
        setError((err as Error).message)
      }
    },
    [refetch, onResolved],
  )

  return { pending: (data ?? []).filter((w) => !resolved.includes(w.id)), error, review }
}
