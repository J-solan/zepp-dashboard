import { describe, expect, it } from 'vitest'
import { formatTooltipTs, timeAxis } from './chartFormat'
import { dayBoundaryTs, dayStartTs, rangeBoundsTs } from './date'

/** Medianoches locales del rango, tal como se las pasa TimeSeriesChart. */
function dayStarts(from: string, to: string): number[] {
  return [dayStartTs(from), ...dayBoundaryTs(from, to)]
}

const HOUR = 3600

describe('timeAxis — vista de un día', () => {
  const [start, end] = rangeBoundsTs('2026-07-24', '2026-07-24')
  const axis = timeAxis(start, end, dayStarts('2026-07-24', '2026-07-24'))

  it('reparte el día en marcas de 3 h', () => {
    expect(axis.ticks).toHaveLength(8)
    expect(axis.ticks[1] - axis.ticks[0]).toBe(3 * HOUR)
  })

  it('arranca en la medianoche local y no pinta el borde final', () => {
    expect(axis.ticks[0]).toBe(start)
    expect(axis.ticks.at(-1)).toBe(end - 3 * HOUR)
  })

  it('etiqueta las marcas como hora', () => {
    expect(axis.format(start)).toBe('00:00')
    expect(axis.format(start + 15 * HOUR)).toBe('15:00')
  })
})

describe('timeAxis — con zoom', () => {
  const midnight = dayStartTs('2026-07-24')

  it('baja a marcas de 15 min al ampliar a 2 h', () => {
    const axis = timeAxis(midnight + 10 * HOUR, midnight + 12 * HOUR, [midnight])
    expect(axis.ticks[1] - axis.ticks[0]).toBe(900)
    expect(axis.format(axis.ticks[0])).toBe('10:00')
  })

  it('baja a marcas de 5 min al ampliar a 30 min', () => {
    const axis = timeAxis(midnight + 10 * HOUR, midnight + 10.5 * HOUR, [midnight])
    expect(axis.ticks[1] - axis.ticks[0]).toBe(300)
  })

  it('alinea con el reloj, no con el borde del zoom', () => {
    // zoom que empieza a las 10:07 -> la primera marca es 10:15, no 10:07
    const axis = timeAxis(midnight + 10 * HOUR + 7 * 60, midnight + 12 * HOUR, [midnight])
    expect(axis.format(axis.ticks[0])).toBe('10:15')
  })
})

describe('timeAxis — vistas multi-día', () => {
  it('en una semana pone una marca por día, con fecha', () => {
    const [start, end] = rangeBoundsTs('2026-07-18', '2026-07-24')
    const axis = timeAxis(start, end, dayStarts('2026-07-18', '2026-07-24'))
    expect(axis.ticks).toEqual([
      dayStartTs('2026-07-18'),
      dayStartTs('2026-07-19'),
      dayStartTs('2026-07-20'),
      dayStartTs('2026-07-21'),
      dayStartTs('2026-07-22'),
      dayStartTs('2026-07-23'),
      dayStartTs('2026-07-24'),
    ])
    // Formato día/mes, no la hora que se usa intradía. (El relleno a dos
    // dígitos depende de los datos de locale, que en Node son reducidos: se
    // comprueba la forma, no el string exacto.)
    // Y el día es el de Madrid: con la zona de la máquina en UTC, la medianoche
    // del 18 se etiquetaba "17/7".
    expect(axis.format(axis.ticks[0])).toMatch(/^18\/0?7$/)
  })

  it('en un mes submuestrea los días para no amontonar etiquetas', () => {
    const [start, end] = rangeBoundsTs('2026-06-25', '2026-07-24')
    const axis = timeAxis(start, end, dayStarts('2026-06-25', '2026-07-24'))
    expect(axis.ticks.length).toBeLessThanOrEqual(8)
    expect(axis.ticks.length).toBeGreaterThan(2)
  })

  it('todas las marcas de día caen en medianoche local, también cruzando el cambio de horario', () => {
    const axis = timeAxis(...rangeBoundsTs('2026-10-23', '2026-10-27'), dayStarts('2026-10-23', '2026-10-27'))
    for (const tick of axis.ticks) {
      expect(new Date(tick * 1000).toLocaleTimeString('es-ES', { timeZone: 'Europe/Madrid' })).toBe('0:00:00')
    }
  })
})

describe('formatTooltipTs', () => {
  it('pinta día y hora de Madrid, no de la zona de la máquina', () => {
    expect(formatTooltipTs(dayStartTs('2026-07-24') + 15.5 * HOUR)).toMatch(/^24\/0?7, 15:30$/)
  })
})
