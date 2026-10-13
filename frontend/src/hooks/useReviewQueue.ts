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
  /** Varias revisiones en orden, una a una; para en la primera que falla. */
  reviewAll: (items: { id: number; body: ReviewBody }[]) => Promise<void>
}

/** Cola de revisión (los 223 sin clasificar) como estado compartido.
 *
 * Vive en un hook y no dentro de `ReviewQueue` porque hay DOS
 * consumidores del mismo dato: el badge de la campana en la cabecera y el
 * panel que se abre al pulsarla. Con un `useApi` en cada uno, clasificar
 * dejaría el badge desfasado hasta el siguiente refetch.
 */
export function useReviewQueue(): ReviewQueue {
  const { data } = useApi<PendingWorkout[]>('/api/workouts/pending')
  // Ids ya resueltos en esta pantalla: se retiran de la lista antes de que
  // conteste el servidor (optimistic) y vuelven si el POST falla.
  const [resolved, setResolved] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)

  // Con cada lista nueva del servidor se olvidan los ids que ya no trae: si no,
  // un entreno que vuelve a pendiente ("Recuperar") seguiría oculto para
  // siempre. Los que aún trae (POST en vuelo) siguen ocultos.
  const [seen, setSeen] = useState(data)
  if (data !== seen) {
    setSeen(data)
    setResolved((ids) => ids.filter((id) => data?.some((w) => w.id === id)))
  }

  // Un POST con su optimistic; true si se guardó. La caché la vacía quien
  // llama, una vez por tanda: aplicar veinte sugerencias no debe repintar la
  // pestaña entera veinte veces.
  const post = useCallback(async (id: number, body: ReviewBody) => {
    setResolved((ids) => [...ids, id])
    try {
      await fetchJson(`/api/workouts/${id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      return true
    } catch (err) {
      setResolved((ids) => ids.filter((x) => x !== id))
      setError((err as Error).message)
      return false
    }
  }, [])

  const review = useCallback(
    async (id: number, body: ReviewBody) => {
      setError(null)
      if (await post(id, body)) clearApiCache()
    },
    [post],
  )

  // Una a una y parando en la primera que falla: el error sale en la cola y lo
  // que quedaba por aplicar sigue ahí, sin estados a medias que adivinar.
  const reviewAll = useCallback(
    async (items: { id: number; body: ReviewBody }[]) => {
      setError(null)
      let saved = 0
      for (const { id, body } of items) {
        if (!(await post(id, body))) break
        saved++
      }
      if (saved > 0) clearApiCache()
    },
    [post],
  )

  return { pending: (data ?? []).filter((w) => !resolved.includes(w.id)), error, review, reviewAll }
}
