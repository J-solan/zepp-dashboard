import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { fetchJson } from '../lib/api'

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

// Caché en memoria por URL: expandir/colapsar una tarjeta
// remonta su detalle, pero si la URL ya se pidió se sirve al instante sin
// refetch. Se vacía tras un sync o una escritura (clearApiCache) porque los
// datos cambian.
const cache = new Map<string, unknown>()

// Vaciar no basta: los useApi ya montados seguirían pintando lo viejo hasta
// remontarse. Cada vaciado sube esta versión y avisa, y todos vuelven a pedir
// su URL a la vez: tras un sync se repinta el Panel entero, y tras clasificar
// un entreno, la lista, la campana y los colores. Quien escribe solo llama a
// clearApiCache; no hace falta (y duplicaría la petición) un refetch detrás.
// Límite conocido: varias instancias con la MISMA URL piden cada una la suya
// (useSports está montado en cinco sitios: cinco GET de /api/sports, que es
// diminuto). Si llegara a importar, compartir las peticiones en vuelo por URL.
let version = 0
const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function clearApiCache(): void {
  cache.clear()
  version++
  listeners.forEach((listener) => listener())
}

export function useApi<T>(path: string): UseApiResult<T> {
  const cacheVersion = useSyncExternalStore(subscribe, () => version)
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
    // cacheVersion: tras un clearApiCache la caché está vacía y esto recarga.
  }, [path, load, cacheVersion])

  const refetch = useCallback(() => {
    cache.delete(path)
    load(path)
  }, [path, load])

  return { data, loading, error, refetch }
}
