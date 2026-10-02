import { describe, expect, it } from 'vitest'
import { dayStartTs } from './date'
import { formatClock } from './format'

describe('formatClock', () => {
  it('da la hora de Madrid, no la de la zona de la máquina', () => {
    expect(formatClock(dayStartTs('2026-07-24') + 22.5 * 3600)).toBe('22:30')
  })
})
