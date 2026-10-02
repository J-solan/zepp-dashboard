import { describe, expect, it } from 'vitest'
import { deviation, quantiles } from './baseline'

describe('quantiles', () => {
  it('devuelve la banda de una serie conocida', () => {
    expect(quantiles([1, 2, 3, 4, 5, 6, 7, 8, 9])).toEqual({
      min: 1,
      p25: 3,
      median: 5,
      p75: 7,
      max: 9,
    })
  })

  it('no depende del orden de entrada', () => {
    expect(quantiles([9, 1, 5, 3, 7])).toEqual(quantiles([1, 3, 5, 7, 9]))
  })

  it('ignora los huecos en vez de contarlos como cero', () => {
    // Un día sin dato NO es un día de cero: cuenta como no medido.
    expect(quantiles([1, null, 5, undefined, 9])).toEqual(quantiles([1, 5, 9]))
  })

  it('con un solo valor, la banda es ese valor', () => {
    expect(quantiles([42])).toEqual({ min: 42, p25: 42, median: 42, p75: 42, max: 42 })
  })

  it('sin ningún dato no hay banda que enseñar', () => {
    expect(quantiles([])).toBeNull()
    expect(quantiles([null, undefined])).toBeNull()
  })
})

describe('deviation', () => {
  const band = { min: 0, p25: 10, median: 20, p75: 30, max: 40 }

  it('mide en múltiplos del rango intercuartílico', () => {
    expect(deviation(20, band)).toBe(0)
    expect(deviation(30, band)).toBe(0.5)
    expect(deviation(0, band)).toBe(-1)
  })

  it('una banda plana no divide por cero', () => {
    expect(deviation(9, { min: 5, p25: 5, median: 5, p75: 5, max: 5 })).toBe(0)
  })
})
