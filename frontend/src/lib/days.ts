import { isoPlusDays } from './date'

export interface DayValue {
  day: string
  value: number | null
}

/** Serie de `days` días consecutivos que ACABA en `last`, tomando de `rows` la
 * fila de cada día.
 *
 * Los días sin fila entran con `value: null` en vez de desaparecer: la rejilla
 * debe tener siempre el mismo número de barras. Si se colapsaran, un día sin
 * ingesta ensancharía las demás y la tarjeta cambiaría de forma según el dato,
 * que es justo lo que no debe pasar.
 */
/** Media de los días CON dato; `null` si no hay ninguno. Los huecos no puntúan:
 * contarlos como 0 hundiría la referencia justo cuando falta ingesta. */
export function seriesMean(data: DayValue[]): number | null {
  const values = data.flatMap((d) => (d.value != null ? [d.value] : []))
  return values.length > 0 ? values.reduce((sum, v) => sum + v, 0) / values.length : null
}

export function daySeries<T extends { day: string }>(
  rows: T[],
  last: string,
  pick: (row: T) => number | null,
  days = 7,
): DayValue[] {
  const byDay = new Map(rows.map((r) => [r.day, r]))
  return Array.from({ length: days }, (_, i) => {
    const day = isoPlusDays(last, i - days + 1)
    const row = byDay.get(day)
    return { day, value: row ? pick(row) : null }
  })
}
