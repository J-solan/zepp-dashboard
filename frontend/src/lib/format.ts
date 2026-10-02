/** Cifras con punto de millar SIEMPRE.
 *
 * `toLocaleString('es-ES')` a secas no agrupa los números de cuatro dígitos
 * (8373 sale sin punto y 11.730 con él), así que una lista de volúmenes o de
 * pasos mezclaba los dos estilos en la misma columna. */
export function formatNumber(value: number): string {
  return Math.round(value).toLocaleString('es-ES', { useGrouping: 'always' })
}

export function formatRelative(tsSeconds: number): string {
  const diffMs = Date.now() - tsSeconds * 1000
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return 'hace un momento'
  if (minutes < 60) return `hace ${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `hace ${hours} h`
  const days = Math.round(hours / 24)
  return `hace ${days} día${days === 1 ? '' : 's'}`
}

/** Hora local "22:31" de un instante unix. */
export function formatClock(tsSeconds: number): string {
  return new Date(tsSeconds * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}

export function formatDuration(minutes: number): string {
  // Menos de un minuto pero más que nada: "0 min" haría creer que no hubo
  // tiempo en esa zona de FC cuando sí lo hubo.
  if (minutes > 0 && minutes < 1) return '<1 min'
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h > 0 ? `${h} h ${m} min` : `${m} min`
}

/** Estado vacío útil: no hay muestras hoy, pero indica cuándo fue el último
 * sync para que se entienda si es "aún no llega" o "algo va mal". */
export function emptyHint(lastSyncTs: number | null): string {
  return lastSyncTs != null ? `sin muestras hoy · sync ${formatRelative(lastSyncTs)}` : 'sin muestras hoy'
}
