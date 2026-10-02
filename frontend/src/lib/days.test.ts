import { describe, expect, it } from 'vitest'
import { daySeries, seriesMean } from './days'

describe('daySeries', () => {
  it('devuelve 7 días consecutivos acabando en hoy, cruzando el cambio de mes', () => {
    const series = daySeries([], '2026-08-01', () => null)
    expect(series.map((d) => d.day)).toEqual([
      '2026-07-26',
      '2026-07-27',
      '2026-07-28',
      '2026-07-29',
      '2026-07-30',
      '2026-07-31',
      '2026-08-01',
    ])
  })

  it('rellena con null los días sin fila y no pierde huecos intermedios', () => {
    const rows = [
      { day: '2026-07-26', steps: 4000 },
      { day: '2026-08-01', steps: 12000 },
    ]
    const series = daySeries(rows, '2026-08-01', (r) => r.steps)
    expect(series).toHaveLength(7)
    expect(series.map((d) => d.value)).toEqual([4000, null, null, null, null, null, 12000])
  })

  it('ignora filas fuera de la ventana', () => {
    const rows = [{ day: '2026-07-01', readiness: 90 }]
    expect(daySeries(rows, '2026-08-01', (r) => r.readiness).every((d) => d.value === null)).toBe(true)
  })
})

describe('seriesMean', () => {
  it('promedia solo los días con dato, sin contar los huecos como 0', () => {
    const rows = [
      { day: '2026-07-31', hr: 50 },
      { day: '2026-08-01', hr: 60 },
    ]
    expect(seriesMean(daySeries(rows, '2026-08-01', (r) => r.hr))).toBe(55)
  })

  it('devuelve null si la ventana no tiene ningún dato', () => {
    expect(seriesMean(daySeries([], '2026-08-01', () => null))).toBeNull()
  })
})
