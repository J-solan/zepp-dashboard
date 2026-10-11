// Zona horaria de la app: la `tz` del config del backend, con la que agrupa los
// días. "Hoy" debe calcularse en esta tz local, no en UTC: cerca de medianoche
// la fecha UTC ya es otra y desalinea el rango pedido al backend respecto al día
// local real. main.tsx la fija desde /api/overview antes del primer render; hasta
// entonces, o si la API no responde, vale la del navegador. Es un `let`
// exportado a propósito: quien la importa ve siempre el valor actual.
export let APP_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone

/** Fija la zona de la app. Una zona que el navegador no conoce lanza RangeError
 * aquí (al resolverla), no en cada formateo posterior. */
export function setAppTz(tz: string): void {
  APP_TZ = new Intl.DateTimeFormat('en-US', { timeZone: tz }).resolvedOptions().timeZone
}

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
  return isoPlusDays(todayISO(), -days)
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

/** Hora de reloj 'YYYY-MM-DDTHH:mm' en APP_TZ (lo que da un `<input
 * type="datetime-local">`) -> unix segundos UTC. NaN si no es una fecha.
 *
 * El desfase se mira dos veces: el primero se toma en un instante que puede
 * caer al otro lado de un cambio de hora (la madrugada del cambio en Madrid,
 * las horas siguientes en América); el segundo ya es el del instante real. */
export function appTimeToTs(local: string): number {
  const asIfUtc = Date.parse(`${local}Z`)
  if (Number.isNaN(asIfUtc)) return NaN // campo vacío o a medias: lo valida quien llama
  const guess = asIfUtc - tzOffsetMs(new Date(asIfUtc))
  return (asIfUtc - tzOffsetMs(new Date(guess))) / 1000
}

/** Medianoche local (APP_TZ) del día ISO dado, en unix segundos UTC. Es el
 * mismo anclaje que usa el backend (`_day_range_ts`), así que los ts de las
 * series caen exactamente dentro de estos límites. */
export function dayStartTs(day: string): number {
  return appTimeToTs(`${day}T00:00`)
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

/** Día ISO desplazado `days` (puede ser negativo) sobre el calendario. Es
 * aritmética de calendario pura y se hace entera en UTC: pasar el resultado por
 * APP_TZ daba el día anterior en zonas con desfase negativo (América), donde la
 * medianoche UTC todavía es "ayer". */
export function isoPlusDays(day: string, days: number): string {
  const [year, month, d] = day.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, d + days)).toISOString().slice(0, 10)
}
