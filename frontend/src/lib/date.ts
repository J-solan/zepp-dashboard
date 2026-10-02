// Zona horaria de la app (misma que ingest/config.toml y backend/api.py
// DEFAULT_TZ): "hoy" debe calcularse en esta tz local, no en UTC. Cerca de
// medianoche (00:00-02:00 en verano) la fecha UTC todavía es la del día
// anterior y desalinea el rango pedido al backend respecto al día local real.
const APP_TZ = 'Europe/Madrid'

function isoInAppTz(date: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: APP_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

export function todayISO(): string {
  return isoInAppTz(new Date())
}

/** Día local (APP_TZ) de un instante unix. Es el mismo criterio con el que el
 * backend agrupa por día, así que un entreno de las 00:30 cae en el día que
 * espera el usuario y no en el anterior por UTC. */
export function dayOfTs(ts: number): string {
  return isoInAppTz(new Date(ts * 1000))
}

export function isoDaysAgo(days: number): string {
  const [year, month, day] = todayISO().split('-').map(Number)
  const anchor = new Date(Date.UTC(year, month - 1, day))
  anchor.setUTCDate(anchor.getUTCDate() - days)
  return isoInAppTz(anchor)
}

/** Nº de días cubiertos por [from, to] local, ambos inclusive. */
export function daySpan(from: string, to: string): number {
  const msPerDay = 86400000
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / msPerDay) + 1
}

/** Desfase de APP_TZ respecto a UTC (ms) en un instante dado. Necesario porque
 * el offset no es fijo: Madrid es UTC+1 en invierno y UTC+2 en verano. */
function tzOffsetMs(at: Date): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: APP_TZ,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(at)
  const get = (type: string) => Number(parts.find((p) => p.type === type)!.value)
  // hour puede venir como 24 para medianoche en el ciclo h23/h24 de algunos ICU.
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour') % 24, get('minute'), get('second'))
  return asUtc - at.getTime()
}

/** Medianoche local (APP_TZ) del día ISO dado, en unix segundos UTC. Es el
 * mismo anclaje que usa el backend (`_day_range_ts`), así que los ts de las
 * series caen exactamente dentro de estos límites. */
export function dayStartTs(day: string): number {
  const [year, month, d] = day.split('-').map(Number)
  const asIfUtc = Date.UTC(year, month - 1, d)
  return (asIfUtc - tzOffsetMs(new Date(asIfUtc))) / 1000
}

/** Límites [inicio, fin) del rango de días local, en unix segundos. `fin` es
 * la medianoche del día SIGUIENTE a `to` (no `inicio + n*86400`, que se
 * desviaría una hora en los días de cambio de horario): encuadra el eje X al
 * día completo aunque solo haya muestras de parte del día. */
export function rangeBoundsTs(from: string, to: string): [number, number] {
  return [dayStartTs(from), dayStartTs(isoPlusDays(to, 1))]
}

/** Medianoches locales interiores del rango (excluye la del primer día, que ya
 * es el borde del eje): separadores de día para las vistas multi-día. */
export function dayBoundaryTs(from: string, to: string): number[] {
  const out: number[] = []
  for (let i = 1; i < daySpan(from, to); i++) out.push(dayStartTs(isoPlusDays(from, i)))
  return out
}

/** Día ISO desplazado `days` (puede ser negativo) sobre el calendario local. */
export function isoPlusDays(day: string, days: number): string {
  const [year, month, d] = day.split('-').map(Number)
  const anchor = new Date(Date.UTC(year, month - 1, d))
  anchor.setUTCDate(anchor.getUTCDate() + days)
  return isoInAppTz(anchor)
}
