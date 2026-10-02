import { useApi } from '../hooks/useApi'
import { isoPlusDays, todayISO } from '../lib/date'
import { daySeries } from '../lib/days'
import type { DailyMetrics } from '../lib/types'

const DAYS = 7

/** Media de los últimos 7 días de una columna de `daily_metrics`, ya formateada
 * para la cabecera de una tarjeta de MÉTRICAS.
 *
 * Es el contexto que faltaba: "21 de estrés" no dice si hoy vas bien o mal
 * hasta que sabes por dónde andas normalmente. Devuelve `undefined` cuando no
 * hay ni un día con dato, para que la tarjeta no enseñe una referencia vacía.
 */
/** Serie de los últimos 7 días de una columna de `daily_metrics`, lista para
 * `WeekBars`. Misma petición que `useWeekReference` (la cachea `useApi`), así
 * que tener las dos en la misma pantalla no dispara dos veces. */
export function useWeekSeries(pick: (row: DailyMetrics) => number | null) {
  const today = todayISO()
  const { data } = useApi<DailyMetrics[]>(
    `/api/daily?from=${isoPlusDays(today, -(DAYS - 1))}&to=${today}`,
  )
  return daySeries(data ?? [], today, pick, DAYS)
}
