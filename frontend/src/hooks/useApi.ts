import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchJson } from '../lib/api'

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

// Caché en memoria por URL: expandir/colapsar una tarjeta
// remonta su detalle, pero si la URL ya se pidió se sirve al instante sin
// refetch. Se vacía tras un sync (clearApiCache) porque los datos cambian.
const cache = new Map<string, unknown>()

export function clearApiCache(): void {
  cache.clear()
}

export function useApi<T>(path: string): UseApiResult<T> {
  const [data, setData] = useState<T | null>(() => (cache.has(path) ? (cache.get(path) as T) : null))
  const [loading, setLoading] = useState(!cache.has(path))
  const [error, setError] = useState<string | null>(null)
  // Fetch en curso: se aborta al cambiar de URL o al refetch, para que una
  // respuesta lenta (p.ej. 30d) no pise el render de otra más reciente (hoy).
  const controllerRef = useRef<AbortController | null>(null)

  const load = useCallback((url: string) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setLoading(true)
    setError(null)
    fetchJson<T>(url, { signal: controller.signal })
      .then((result) => {
        cache.set(url, result)
        setData(result)
        setLoading(false)
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return // cancelado: lo continúa el nuevo fetch
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (cache.has(path)) {
      controllerRef.current?.abort()
      setData(cache.get(path) as T)
      setLoading(false)
      setError(null)
      return
    }
    load(path)
    return () => controllerRef.current?.abort()
  }, [path, load])

  const refetch = useCallback(() => {
    cache.delete(path)
    load(path)
  }, [path, load])

  return { data, loading, error, refetch }
}
