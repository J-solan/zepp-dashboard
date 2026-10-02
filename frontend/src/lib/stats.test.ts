import { describe, expect, it } from 'vitest'
import { pearson } from './stats'

describe('pearson', () => {
  it('mide 1 cuando una serie sigue a la otra', () => {
    expect(pearson([1, 2, 3], [2, 4, 6])).toBe(1)
  })

  it('mide −1 cuando una sube y la otra baja', () => {
    expect(pearson([1, 2, 3], [6, 4, 2])).toBe(-1)
  })

  it('solo cruza los días en los que hay las dos medidas', () => {
    // El 99 es de un día sin la otra medida: no debe entrar en la cuenta.
    expect(pearson([1, null, 3, 5], [2, 99, 6, 10])).toBe(1)
  })

  it('una serie sin variación no correlaciona con nada', () => {
    expect(pearson([1, 2, 3, 4], [5, 5, 5, 5])).toBeNull()
  })

  it('con menos de tres pares no se afirma nada', () => {
    expect(pearson([1, 2], [2, 4])).toBeNull()
  })
})
