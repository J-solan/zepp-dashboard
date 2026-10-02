import { describe, expect, it } from 'vitest'
import { accentPct, muscleFill } from './muscleScale'

describe('accentPct', () => {
  it('el músculo más trabajado del rango es acento pleno y el no tocado, neutro', () => {
    expect(accentPct(3200, 3200)).toBe(100)
    expect(accentPct(0, 3200)).toBe(0)
  })

  it('sube del suelo al 100 % en proporción al volumen', () => {
    // 12 + 88 * 0,5 = 56
    expect(accentPct(1600, 3200)).toBe(56)
    expect(accentPct(800, 3200)).toBe(34)
  })

  it('un volumen mínimo se sigue distinguiendo de la ausencia', () => {
    expect(accentPct(1, 3200)).toBeGreaterThanOrEqual(12)
  })

  it('es monótona: más volumen nunca pinta menos', () => {
    const pcts = [0, 100, 500, 2000, 3200].map((v) => accentPct(v, 3200))
    expect(pcts).toEqual([...pcts].sort((a, b) => a - b))
  })

  it('un rango sin fuerza (max 0) no tiñe nada', () => {
    expect(accentPct(0, 0)).toBe(0)
    expect(muscleFill(0, 0)).toContain('var(--color-page)') // tono del cuerpo, sin acento
    expect(muscleFill(0, 0)).not.toContain('--color-accent')
  })

  it('acota si el volumen supera el máximo declarado', () => {
    expect(accentPct(9999, 3200)).toBe(100)
  })
})
