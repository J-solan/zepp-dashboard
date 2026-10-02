import { describe, expect, it } from 'vitest'
import { areaPath, barsPath, gapPath, linePath } from './series'

// Escala de juguete: un punto cada 10 px y el valor medido desde abajo.
const x = (i: number) => i * 10
const y = (v: number) => 100 - v

describe('linePath', () => {
  it('une los puntos consecutivos', () => {
    expect(linePath([0, 10, 20], x, y)).toBe('M0 100L10 90L20 80')
  })

  it('un hueco parte el trazo: la línea no cruza lo que no se midió', () => {
    expect(linePath([0, null, 20], x, y)).toBe('M0 100M20 80')
  })

  it('sin datos devuelve un path vacío, no uno inválido', () => {
    expect(linePath([null, null], x, y)).toBe('')
  })
})

describe('gapPath', () => {
  it('tiende un puente entre los extremos de cada hueco', () => {
    expect(gapPath([0, null, 20], x, y)).toBe('M0 100L20 80')
  })

  it('sin huecos no hay puentes', () => {
    expect(gapPath([0, 10, 20], x, y)).toBe('')
  })
})

describe('areaPath', () => {
  it('cierra contra la base', () => {
    expect(areaPath([0, 10], x, y, 100)).toBe('M0 100L0 100L10 90L10 100Z')
  })

  it('cada tramo con dato se cierra por su cuenta', () => {
    // Dos "Z": el relleno tampoco cruza el hueco.
    expect(areaPath([0, null, 20], x, y, 100).match(/Z/g)).toHaveLength(2)
  })
})

describe('barsPath', () => {
  const opts = { baseY: 100, height: 100, max: 100, width: 4 }

  it('dibuja una barra por valor, centrada en su x', () => {
    expect(barsPath([50], x, opts)).toBe('M-2 50h4v50h-4Z')
  })

  it('recorta al techo en vez de desbordar el carril', () => {
    // 200 con techo 100: la barra llega al tope y se queda ahí. El valor real
    // se rotula aparte; aplastar el resto de la serie para que quepa el pico
    // sería peor.
    expect(barsPath([200], x, opts)).toBe('M-2 0h4v100h-4Z')
  })

  it('ni los huecos ni los ceros pintan barra', () => {
    expect(barsPath([null, 0, undefined], x, opts)).toBe('')
  })
})
