import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { dayBoundaryTs, dayStartTs, isoDaysAgo, isoPlusDays, rangeBoundsTs, todayISO } from './date'

describe('todayISO', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('usa el día local (Europe/Madrid), no el día UTC, en la franja 00:00-02:00 de verano (CEST)', () => {
    // 2026-07-24T23:30:00Z = 2026-07-25T01:30 en Madrid (CEST, UTC+2):
    // el día UTC todavía es 24, pero el día local ya es 25.
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-24T23:30:00Z'))

    expect(todayISO()).toBe('2026-07-25')
  })

  it('usa el día local (Europe/Madrid), no el día UTC, en la franja 00:00-01:00 de invierno (CET)', () => {
    // 2026-01-15T23:30:00Z = 2026-01-16T00:30 en Madrid (CET, UTC+1).
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-15T23:30:00Z'))

    expect(todayISO()).toBe('2026-01-16')
  })

  it('coincide con el día UTC fuera de la franja de desalineación', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-24T15:44:00Z'))

    expect(todayISO()).toBe('2026-07-24')
  })
})

describe('isoDaysAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-24T15:44:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resta días sobre el día local, no el UTC', () => {
    expect(isoDaysAgo(0)).toBe(todayISO())
    expect(isoDaysAgo(1)).toBe('2026-07-23')
    expect(isoDaysAgo(6)).toBe('2026-07-18')
  })

  it('cruza el límite de mes correctamente', () => {
    vi.setSystemTime(new Date('2026-08-01T10:00:00Z'))
    expect(isoDaysAgo(3)).toBe('2026-07-29')
  })

  it('también respeta el día local cerca de medianoche UTC', () => {
    // 2026-07-24T23:30:00Z -> hoy local = 2026-07-25 (ver test de todayISO)
    vi.setSystemTime(new Date('2026-07-24T23:30:00Z'))
    expect(isoDaysAgo(6)).toBe('2026-07-19')
  })
})

describe('dayStartTs', () => {
  it('ancla en la medianoche LOCAL, no en la UTC (verano, CEST = UTC+2)', () => {
    // 2026-07-24 00:00 en Madrid = 2026-07-23T22:00:00Z
    expect(dayStartTs('2026-07-24')).toBe(Date.parse('2026-07-23T22:00:00Z') / 1000)
  })

  it('ancla en la medianoche LOCAL en invierno (CET = UTC+1)', () => {
    expect(dayStartTs('2026-01-15')).toBe(Date.parse('2026-01-14T23:00:00Z') / 1000)
  })

  it('acierta el día del cambio de horario de primavera (2026-03-29, día de 23 h)', () => {
    expect(dayStartTs('2026-03-29')).toBe(Date.parse('2026-03-28T23:00:00Z') / 1000)
    // el día siguiente ya arranca con offset +2 -> solo 23 h de diferencia
    expect(dayStartTs('2026-03-30') - dayStartTs('2026-03-29')).toBe(23 * 3600)
  })

  it('acierta el día del cambio de horario de otoño (2026-10-25, día de 25 h)', () => {
    expect(dayStartTs('2026-10-26') - dayStartTs('2026-10-25')).toBe(25 * 3600)
  })
})

describe('rangeBoundsTs', () => {
  it('encuadra un solo día completo: 24 h aunque no haya muestras', () => {
    const [start, end] = rangeBoundsTs('2026-07-24', '2026-07-24')
    expect(start).toBe(dayStartTs('2026-07-24'))
    expect(end - start).toBe(24 * 3600)
  })

  it('el fin es exclusivo: medianoche del día siguiente a `to`', () => {
    const [, end] = rangeBoundsTs('2026-07-18', '2026-07-24')
    expect(end).toBe(dayStartTs('2026-07-25'))
  })

  it('no asume 86400 s/día al cruzar el cambio de horario', () => {
    const [start, end] = rangeBoundsTs('2026-10-24', '2026-10-26')
    expect(end - start).toBe((24 + 25 + 24) * 3600)
  })
})

describe('dayBoundaryTs', () => {
  it('devuelve las medianoches interiores, sin la del primer día', () => {
    expect(dayBoundaryTs('2026-07-22', '2026-07-24')).toEqual([
      dayStartTs('2026-07-23'),
      dayStartTs('2026-07-24'),
    ])
  })

  it('no hay separadores dentro de un solo día', () => {
    expect(dayBoundaryTs('2026-07-24', '2026-07-24')).toEqual([])
  })
})

describe('isoPlusDays', () => {
  it('avanza y retrocede cruzando el límite de mes', () => {
    expect(isoPlusDays('2026-07-31', 1)).toBe('2026-08-01')
    expect(isoPlusDays('2026-08-01', -1)).toBe('2026-07-31')
  })

  it('cruza el cambio de horario sin saltarse ni repetir día', () => {
    expect(isoPlusDays('2026-03-28', 1)).toBe('2026-03-29')
    expect(isoPlusDays('2026-10-24', 1)).toBe('2026-10-25')
  })
})
