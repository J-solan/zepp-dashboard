import { useCallback, useMemo } from 'react'
import { clearApiCache, useApi } from './useApi'
import { fetchJson } from '../lib/api'
import type { SportStyles } from '../lib/workouts'

export interface Sport {
  name: string
  /** `null` = sin color elegido; el front cae en su hash determinista. */
  color: string | null
}

export interface SportsResult {
  sports: Sport[]
  /** Solo los que tienen color, listo para `sportColor(sport, styles)`. */
  styles: SportStyles
  save: (name: string, color: string | null) => Promise<void>
  remove: (name: string) => Promise<void>
  reload: () => void
}

/** Etiquetas de deporte y sus colores (`/api/sports`).
 *
 * `useApi` cachea por URL, así que aunque varios componentes llamen a este hook
 * solo se pide una vez. Tras escribir se vacía la caché entera: el color de una
 * etiqueta aparece en la lista, en los filtros y en el editor a la vez.
 */
export function useSports(): SportsResult {
  const { data, refetch } = useApi<Sport[]>('/api/sports')
  const sports = useMemo(() => data ?? [], [data])

  const styles = useMemo(
    () =>
      Object.fromEntries(
        sports.filter((s) => s.color).map((s) => [s.name, s.color as string]),
      ) as SportStyles,
    [sports],
  )

  const write = useCallback(
    async (path: string, init: RequestInit) => {
      await fetchJson(path, init)
      clearApiCache()
      refetch()
    },
    [refetch],
  )

  const save = useCallback(
    (name: string, color: string | null) =>
      write(`/api/sports/${encodeURIComponent(name)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ color }),
      }),
    [write],
  )

  const remove = useCallback(
    (name: string) => write(`/api/sports/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    [write],
  )

  return { sports, styles, save, remove, reload: refetch }
}
