import { useCallback } from 'react'
import { fetchJson } from '../lib/api'
import { clearApiCache, useApi } from './useApi'
import type { DateRange } from '../lib/dateRange'
import type { Annotation } from '../lib/types'

export interface UseAnnotationsResult {
  annotations: Annotation[]
  error: string | null
  create: (start_ts: number, end_ts: number, text: string) => Promise<void>
  remove: (id: number) => Promise<void>
}

/** Anotaciones del rango visible, con alta y baja.
 *
 * Tras escribir se vacía la caché de `useApi` y se refetchea: la misma nota
 * sale en la gráfica de FC y en la de estrés, que son componentes hermanos sin
 * estado compartido, y si no se invalida la caché una se quedaría desfasada. */
export function useAnnotations(range: DateRange): UseAnnotationsResult {
  const path = `/api/annotations?from=${range.from}&to=${range.to}`
  const { data, error, refetch } = useApi<Annotation[]>(path)

  const create = useCallback(
    async (start_ts: number, end_ts: number, text: string) => {
      await fetchJson<Annotation>('/api/annotations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_ts, end_ts, text }),
      })
      clearApiCache()
      refetch()
    },
    [refetch],
  )

  const remove = useCallback(
    async (id: number) => {
      await fetchJson<void>(`/api/annotations/${id}`, { method: 'DELETE' })
      clearApiCache()
      refetch()
    },
    [refetch],
  )

  return { annotations: data ?? [], error, create, remove }
}
