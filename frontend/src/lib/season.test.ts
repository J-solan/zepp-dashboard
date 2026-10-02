import { describe, expect, it } from 'vitest'
import { bucketOf, findings, monthGrid, monthlySummary, quintileCuts, weekdayMedians } from './season'
import type { DailyMetrics, SleepSession, Workout } from './types'

const daily = (day: string, extra: Partial<DailyMetrics> = {}): DailyMetrics => ({
  day,
  steps: null,
  calories: null,
  resting_hr: null,
  readiness: null,
  hrv_ms: null,
  respiratory_rate: null,
  stress_avg: null,
  vo2max: null,
  train_load: null,
  tz: null,
  ...extra,
})

const workout = (day: string, load: number | null = 10): Workout =>
  ({
    id: Math.random(),
    source: 'zepp',
    start_ts: Date.parse(`${day}T10:00:00Z`) / 1000,
    end_ts: Date.parse(`${day}T11:00:00Z`) / 1000,
    train_load: load,
    effective_sport: 'fuerza',
    hr_zones: [],
  }) as unknown as Workout

describe('monthGrid', () => {
  it('coloca el día 1 en su día de la semana real, con el lunes como primera columna', () => {
    // El 1 de julio de 2026 cae en miércoles: tercera columna.
    const july = monthGrid(2026, 7)
    expect(july).toHaveLength(31)
    expect(july[0]).toEqual({ day: '2026-07-01', col: 2, row: 0 })
  })

  it('un mes que empieza en domingo ocupa la última columna de la primera fila', () => {
    // 1 de marzo de 2026, domingo.
    expect(monthGrid(2026, 3)[0]).toEqual({ day: '2026-03-01', col: 6, row: 0 })
  })

  it('salta de fila al pasar el domingo', () => {
    const july = monthGrid(2026, 7)
    expect(july[4]).toEqual({ day: '2026-07-05', col: 6, row: 0 })
    expect(july[5]).toEqual({ day: '2026-07-06', col: 0, row: 1 })
  })
})

describe('quintileCuts', () => {
  it('parte la serie en cinco tramos por sus propios valores', () => {
    const cuts = quintileCuts([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(cuts).toHaveLength(4)
    expect(bucketOf(1, cuts)).toBe(0)
    expect(bucketOf(10, cuts)).toBe(4)
  })

  it('sin datos no hay cortes y todo cae en el primer tramo', () => {
    expect(quintileCuts([])).toEqual([])
    expect(bucketOf(5, [])).toBe(0)
  })
})

describe('weekdayMedians', () => {
  it('agrupa por día de la semana empezando en lunes', () => {
    // 2026-08-03 y 2026-08-10 son lunes; 2026-08-04, martes.
    const rows = [
      daily('2026-08-03', { readiness: 70 }),
      daily('2026-08-10', { readiness: 80 }),
      daily('2026-08-04', { readiness: 90 }),
    ]
    const medians = weekdayMedians(rows, (r) => r.readiness)
    // Mediana por rango más cercano: con dos valores se queda con el de abajo.
    expect(medians[0]).toBe(70) // lunes
    expect(medians[1]).toBe(90) // martes
    expect(medians[6]).toBeNull() // domingo, sin datos
  })
})

describe('monthlySummary', () => {
  it('resume cada mes con sus medianas y sus sumas', () => {
    const rows = [
      daily('2026-07-01', { readiness: 80, train_load: 10 }),
      daily('2026-07-02', { readiness: 90, train_load: 5 }),
      daily('2026-08-01', { readiness: 60, train_load: 0 }),
    ]
    const summary = monthlySummary(rows, [], [workout('2026-07-01'), workout('2026-08-01')])
    expect(summary).toHaveLength(2)
    expect(summary[0]).toMatchObject({ month: '2026-07', days: 2, readiness: 80, load: 15, workouts: 1 })
    expect(summary[1]).toMatchObject({ month: '2026-08', days: 1, readiness: 60, load: 0, workouts: 1 })
  })
})

describe('findings', () => {
  it('encuentra la racha más larga por encima de la mediana', () => {
    const rows = [
      daily('2026-08-01', { readiness: 60 }),
      daily('2026-08-02', { readiness: 60 }),
      daily('2026-08-03', { readiness: 90 }),
      daily('2026-08-04', { readiness: 91 }),
      daily('2026-08-05', { readiness: 92 }),
      daily('2026-08-06', { readiness: 93 }),
    ]
    const streak = findings(rows, [], []).find((f) => f.id === 'racha')
    expect(streak?.figure).toBe('3 d')
  })

  it('encuentra el tramo más largo sin entrenar', () => {
    const rows = ['2026-08-01', '2026-08-02', '2026-08-03', '2026-08-04'].map((d) => daily(d, { readiness: 70 }))
    const gap = findings(rows, [], [workout('2026-08-01')]).find((f) => f.id === 'parón')
    expect(gap?.figure).toBe('3 d')
  })

  it('no inventa hallazgos cuando no hay datos', () => {
    expect(findings([], [], [])).toEqual([])
  })
})

describe('monthlySummary con noches incompletas', () => {
  it('acepta noches sin score sin romperse', () => {
    const nights = [{ day: '2026-08-01', score: null } as unknown as SleepSession]
    expect(() => monthlySummary([daily('2026-08-01')], nights, [])).not.toThrow()
  })
})
