import { AlertIcon, CheckIcon, RefreshIcon, SpinnerIcon } from './icons'
import { formatRelative } from '../lib/format'

const STALE_SECONDS = 24 * 3600

interface SyncBannerProps {
  isSyncing: boolean
  triggerError: string | null
  trigger: () => void
  lastSync: { ts: number | null; status: 'ok' | 'error' | 'unknown' }
}

/** Banner compacto de sync: estado + botón en una sola fila (antes era un panel
 * entero). Warn cuando falló, está obsoleto (>24 h) o nunca sincronizó. */
export function SyncBanner({ isSyncing, triggerError, trigger, lastSync }: SyncBannerProps) {
  const isError = lastSync.status === 'error' || triggerError != null
  const ageSeconds = lastSync.ts != null ? Date.now() / 1000 - lastSync.ts : null
  const isStale = ageSeconds != null && ageSeconds > STALE_SECONDS
  const warn = isError || isStale || lastSync.ts == null

  let text: string
  if (isSyncing) text = 'Sincronizando…'
  else if (triggerError) text = triggerError
  else if (lastSync.ts == null) text = 'Sin sincronizaciones todavía'
  else if (isError) text = `Falló · último OK ${formatRelative(lastSync.ts)}`
  else text = `Sync ${formatRelative(lastSync.ts)}`

  // En estado normal es una línea de estado, no una tarjeta: el sync no es
  // contenido, es un dato de servicio. Solo cuando hay algo que avisar se
  // convierte en bloque con color.
  return (
    <div
      className={`flex items-center gap-2 px-1 py-1 ${
        warn ? 'rounded-card bg-warn/10 px-3 py-2' : ''
      }`}
    >
      {isSyncing ? (
        <SpinnerIcon className="h-4 w-4 shrink-0 text-ink-secondary" />
      ) : warn ? (
        <AlertIcon className="h-4 w-4 shrink-0 text-warn" />
      ) : (
        <CheckIcon className="h-4 w-4 shrink-0 text-ok" />
      )}
      <span className={`flex-1 truncate text-xs ${warn ? 'text-warn' : 'text-ink-muted'}`}>{text}</span>
      <button
        type="button"
        onClick={trigger}
        disabled={isSyncing}
        aria-label="Sincronizar ahora"
        className="flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-ink-secondary
                   transition-colors hover:bg-raised hover:text-ink disabled:opacity-50
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <RefreshIcon className={`h-3.5 w-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
        Sync
      </button>
    </div>
  )
}
