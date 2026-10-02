import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { presetRange, rangeLabel, shiftRange } from './dateRange'

// Hoy = 2026-07-24 (local Madrid) en todo el fichero.
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-07-24T15:44:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('presetRange', () => {
  it('ancla la ventana en hoy por defecto', () => {
    expect(presetRange('day')).toEqual({ from: '2026-07-24', to: '2026-07-24' })
    expect(presetRange('week')).toEqual({ from: '2026-07-18', to: '2026-07-24' })
    expect(presetRange('month')).toEqual({ from: '2026-06-25', to: '2026-07-24' })
  })

  it('re-ancla en el día que se le pase: cambiar de granularidad no te devuelve a hoy', () => {
    expect(presetRange('week', '2026-07-10')).toEqual({ from: '2026-07-04', to: '2026-07-10' })
  })
})

describe('shiftRange', () => {
  it('retrocede una ventana entera, sin solapar con la anterior', () => {
    expect(shiftRange(presetRange('week'), 'week', -1)).toEqual({ from: '2026-07-11', to: '2026-07-17' })
  })

  it('retrocede un día en la vista de día', () => {
    expect(shiftRange(presetRange('day'), 'day', -1)).toEqual({ from: '2026-07-23', to: '2026-07-23' })
  })

  it('devuelve null hacia adelante cuando ya se está en hoy (la flecha se deshabilita)', () => {
    expect(shiftRange(presetRange('day'), 'day', 1)).toBeNull()
    expect(shiftRange(presetRange('week'), 'week', 1)).toBeNull()
  })

  it('avanza si hay futuro disponible dentro del pasado', () => {
    expect(shiftRange({ from: '2026-07-10', to: '2026-07-10' }, 'day', 1)).toEqual({
      from: '2026-07-11',
      to: '2026-07-11',
    })
  })

  it('no permite avanzar a un rango que se pasaría de hoy', () => {
    // ventana de 7 d que acaba el 20: avanzar la llevaría al 27 (futuro)
    expect(shiftRange({ from: '2026-07-14', to: '2026-07-20' }, 'week', 1)).toBeNull()
  })

  it('en "custom" el paso es el ancho real del rango elegido', () => {
    expect(shiftRange({ from: '2026-07-01', to: '2026-07-03' }, 'custom', -1)).toEqual({
      from: '2026-06-28',
      to: '2026-06-30',
    })
  })

  it('cruza los cambios de horario sin descuadrarse', () => {
    // primavera 2026 (día de 23 h) y otoño 2025 (día de 25 h)
    expect(shiftRange({ from: '2026-03-29', to: '2026-03-29' }, 'day', -1)).toEqual({
      from: '2026-03-28',
      to: '2026-03-28',
    })
    expect(shiftRange({ from: '2025-10-26', to: '2025-10-26' }, 'day', -1)).toEqual({
      from: '2025-10-25',
      to: '2025-10-25',
    })
  })

  it('nunca deja un rango en el futuro, ni retrocediendo desde uno futuro', () => {
    expect(shiftRange({ from: '2026-12-01', to: '2026-12-01' }, 'day', -1)).toBeNull()
  })
})

describe('rangeLabel', () => {
  it('nombra el día actual y el anterior', () => {
    expect(rangeLabel({ from: '2026-07-24', to: '2026-07-24' })).toBe('Hoy')
    expect(rangeLabel({ from: '2026-07-23', to: '2026-07-23' })).toBe('Ayer')
  })

  it('usa la fecha para cualquier otro día suelto', () => {
    expect(rangeLabel({ from: '2026-07-10', to: '2026-07-10' })).not.toMatch(/Hoy|Ayer/)
  })

  it('describe un tramo con sus dos extremos', () => {
    const label = rangeLabel({ from: '2026-07-18', to: '2026-07-24' })
    expect(label).toContain('–')
    expect(label).toMatch(/18/)
    expect(label).toMatch(/24/)
  })
})
