import { describe, expect, it } from 'vitest'
// `?raw` de Vite en vez de node:fs: el proyecto de la app no lleva tipos de
// Node y este test no es motivo para metérselos.
import toml from '../../../ingest/muscle_map.toml?raw'
import { BACK, FRONT, NEUTRAL_BACK, NEUTRAL_FRONT, VIEW_BOX_BACK, VIEW_BOX_FRONT } from './bodyShapes'

// El vocabulario está DECLARADO en la cabecera del TOML (sus tablas son
// ejercicios, no músculos): "...consistentes entre ejercicios: pecho, dorsal,
// … gemelo." Si alguien reescribe ese comentario, este test cae y hay que
// mirarlo — es justo el aviso que se quiere.
const declared = toml
  .match(/ejercicios:\s*([^.]+)\./)![1]
  .replace(/[#\n]/g, ' ')
  .split(',')
  .map((muscle) => muscle.trim())
  .filter(Boolean)

// Músculos que algún ejercicio del mapa usa de verdad ("pecho = 1.0").
const used = [...new Set([...toml.matchAll(/^(\w+) = [\d.]+$/gm)].map((m) => m[1]))]

const figure = [...new Set([...Object.keys(FRONT), ...Object.keys(BACK)])]

describe('figura del body-map', () => {
  it('dibuja exactamente el vocabulario de muscle_map.toml, ni más ni menos', () => {
    expect([...figure].sort()).toEqual([...declared].sort())
  })

  it('no deja sin dibujar ningún músculo que el mapa asigne a un ejercicio', () => {
    expect(used.filter((muscle) => !figure.includes(muscle))).toEqual([])
  })

  it.each([
    ['frontal', VIEW_BOX_FRONT, [...NEUTRAL_FRONT, ...Object.values(FRONT).flat()]],
    ['posterior', VIEW_BOX_BACK, [...NEUTRAL_BACK, ...Object.values(BACK).flat()]],
  ])('la vista %s cabe en su propio lienzo', (_name, box, paths) => {
    const [bx, by, bw, bh] = (box as string).split(' ').map(Number)
    const outside = (paths as string[]).flatMap((d) =>
      [...d.matchAll(/(-?[\d.]+),(-?[\d.]+)/g)].filter(
        (m) =>
          Number(m[1]) < bx || Number(m[1]) > bx + bw || Number(m[2]) < by || Number(m[2]) > by + bh,
      ),
    )
    expect(outside).toEqual([])
  })
})
