import { describe, expect, it } from 'vitest'
import { dayStartTs, setAppTz } from './date'
import { formatClock } from './format'

describe('formatClock', () => {
  it('da la hora de Madrid, no la de la zona de la máquina', () => {
    expect(formatClock(dayStartTs('2026-07-24') + 22.5 * 3600)).toBe('22:30')
  })

  it('sigue la zona fijada en marcha, no la que había al cargar el módulo', () => {
    setAppTz('America/New_York')
    try {
      expect(formatClock(Date.parse('2026-07-24T22:30:00Z') / 1000)).toBe('18:30')
    } finally {
      setAppTz('Europe/Madrid')
    }
  })
})
