import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch, fetchJson } from '../lib/api'
import { clearApiCache } from './useApi'
import type { SyncStatus } from '../lib/types'

const POLL_MS = 2000

/** Dispara /api/sync y sondea /api/sync/status hasta que termine (ok/error). */
export function useSync(onFinished: () => void) {
  const [status, setStatus] = useState<SyncStatus | null>(null)
  const [triggerError, setTriggerError] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)
  const onFinishedRef = useRef(onFinished)
  onFinishedRef.current = onFinished

  // Al montar: si ya hay un sync en curso (p.ej. tras recargar la página),
  // engancharse al polling en vez de mostrar el botón como si nada pasara.
  useEffect(() => {
    fetchJson<SyncStatus>('/api/sync/status')
      .then((s) => {
        setStatus(s)
        if (s.status === 'running') setPolling(true)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!polling) return
    const id = setInterval(() => {
      fetchJson<SyncStatus>('/api/sync/status')
        .then((s) => {
          setStatus(s)
          if (s.status !== 'running') {
            setPolling(false)
            clearApiCache() // el sync cambió los datos: invalida la caché por URL
            onFinishedRef.current()
          }
        })
        .catch((err: Error) => {
          setTriggerError(err.message)
          setPolling(false)
        })
    }, POLL_MS)
    return () => clearInterval(id)
  }, [polling])

  const trigger = useCallback(async () => {
    setTriggerError(null)
    try {
      const res = await apiFetch('/api/sync', { method: 'POST' })
      // 409 = ya hay un sync en curso (otra pestaña, o el cron). No es un
      // error para el usuario, pero su cuerpo es `{detail}` y NO un SyncStatus:
      // engancharse al polling sin tocar `status`, que lo trae el sondeo.
      if (res.status === 409) {
        setPolling(true)
        return
      }
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail ?? `Error ${res.status}`)
      }
      const body: SyncStatus = await res.json()
      setStatus(body)
      setPolling(true)
    } catch (err) {
      setTriggerError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  return {
    status,
    isSyncing: polling || status?.status === 'running',
    triggerError,
    trigger,
  }
}
