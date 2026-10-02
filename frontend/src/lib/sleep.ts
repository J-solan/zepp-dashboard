import type { SleepSession } from './types'

// mode 4=ligero 5=profundo 7=despierto 8=REM (ver docs/zepp-api.md)
export const STAGE_LABELS: Record<number, string> = {
  4: 'Ligero',
  5: 'Profundo',
  7: 'Despierto',
  8: 'REM',
}

export const STAGE_COLORS: Record<number, string> = {
  4: 'var(--color-stage-light)',
  5: 'var(--color-stage-deep)',
  7: 'var(--color-stage-wake)',
  8: 'var(--color-stage-rem)',
}

/** Una fila por día: la sesión más larga (sueño principal, descarta siestas
 * cortas) para que el hipnograma y la tendencia semanal no salten entre
 * varios puntos el mismo día. */
export function mainSessionPerDay(sessions: SleepSession[]): SleepSession[] {
  const byDay = new Map<string, SleepSession>()
  for (const s of sessions) {
    if (s.is_nap) continue
    const duration = s.end_ts - s.start_ts
    const existing = byDay.get(s.day)
    if (!existing || duration > existing.end_ts - existing.start_ts) {
      byDay.set(s.day, s)
    }
  }
  return [...byDay.values()].sort((a, b) => a.start_ts - b.start_ts)
}
