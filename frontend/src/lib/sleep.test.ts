import { describe, expect, it } from 'vitest'
import { mainSessionPerDay, napsOf } from './sleep'
import type { SleepSession } from './types'

function session(overrides: Partial<SleepSession>): SleepSession {
  return {
    id: 1,
    day: '2026-08-01',
    start_ts: 0,
    end_ts: 100,
    score: 80,
    deep_min: null,
    light_min: null,
    rem_min: null,
    awake_min: null,
    wake_count: null,
    resting_hr: null,
    tz: 'Europe/Madrid',
    is_nap: false,
    stages: [],
    ...overrides,
  }
}

describe('mainSessionPerDay', () => {
  it('descarta las siestas aunque duren más que el sueño nocturno', () => {
    const night = session({ id: 1, start_ts: 0, end_ts: 100, is_nap: false })
    const nap = session({ id: 2, start_ts: 200, end_ts: 500, is_nap: true })
    const [main] = mainSessionPerDay([night, nap])
    expect(main.id).toBe(1)
  })

  it('un día solo con siestas no aparece', () => {
    const nap = session({ id: 2, day: '2026-08-01', start_ts: 200, end_ts: 500, is_nap: true })
    expect(mainSessionPerDay([nap])).toHaveLength(0)
  })
})

describe('napsOf', () => {
  it('solo las siestas de ese día, por hora de inicio', () => {
    const night = session({ id: 1, day: '2026-08-01', start_ts: 0, is_nap: false })
    const late = session({ id: 2, day: '2026-08-01', start_ts: 900, is_nap: true })
    const early = session({ id: 3, day: '2026-08-01', start_ts: 500, is_nap: true })
    const otherDay = session({ id: 4, day: '2026-08-02', start_ts: 700, is_nap: true })
    expect(napsOf('2026-08-01', [late, night, otherDay, early]).map((s) => s.id)).toEqual([3, 2])
  })
})
