import { describe, expect, it } from 'vitest'
import { SPORT, ZONE_RAMP } from './palette'
import {
  effectiveFilter,
  groupByDay,
  sessionVolume,
  sportColor,
  sportLabel,
  suggestedSports,
  zoneBands,
} from './workouts'
import type { HrZone, Workout } from './types'

const zones: HrZone[] = [
  { seconds: 4, threshold: 78 },
  { seconds: 405, threshold: 106 },
  { seconds: 0, threshold: 120 },
  { seconds: 80, threshold: 134 },
]

describe('zoneBands', () => {
  it('rotula cada zona con su tramo: la primera con techo, el resto suelo–techo', () => {
    expect(zoneBands(zones).map((z) => z.label)).toEqual(['≤ 78', '78–106', '120–134'])
  })

  it('reparte la proporción sobre el total y descarta las zonas vacías', () => {
    const bands = zoneBands(zones)
    expect(bands).toHaveLength(3)
    expect(bands.reduce((sum, z) => sum + z.share, 0)).toBeCloseTo(1)
    expect(bands[1].share).toBeCloseTo(405 / 489)
  })

  it('sin tiempo registrado no hay barra que pintar', () => {
    expect(zoneBands([])).toEqual([])
    expect(zoneBands([{ seconds: 0, threshold: 90 }])).toEqual([])
  })
})

describe('zoneBands · color', () => {
  // El strap manda 6 zonas y la rampa tiene 4 colores: con redondeo salían dos
  // azules y dos naranjas seguidos y la barra parecía de dos bloques.
  const six: HrZone[] = [98, 118, 137, 157, 177, 197].map((threshold, i) => ({
    seconds: 60 * (i + 1),
    threshold,
  }))

  it('da un color distinto a cada zona aunque haya más zonas que colores', () => {
    const colors = zoneBands(six).map((z) => z.color)
    expect(colors).toHaveLength(6)
    expect(new Set(colors).size).toBe(6)
  })

  it('empieza en el extremo suave de la rampa y acaba en el duro', () => {
    const colors = zoneBands(six).map((z) => z.color)
    expect(colors[0]).toBe(ZONE_RAMP[0])
    expect(colors.at(-1)).toBe(ZONE_RAMP.at(-1))
  })
})

describe('sportLabel', () => {
  it('distingue "no clasificado" de "otro"', () => {
    expect(sportLabel(null)).toBe('Sin clasificar')
    expect(sportLabel('otro')).toBe('Otro')
    expect(sportLabel('voley_playa')).toBe('Vóley playa')
  })
})

describe('sportColor', () => {
  it('un tipo conocido usa su color fijo, y ninguno es el acento de la app', () => {
    expect(sportColor('fuerza')).toBe(SPORT.fuerza)
    expect(sportColor(null)).toBe(SPORT.otro)
    expect(Object.values(SPORT)).not.toContain('var(--color-accent)')
  })

  it('el texto libre es determinista: mismo deporte, mismo color siempre', () => {
    expect(sportColor('pádel')).toBe(sportColor('pádel'))
    // Normalizado: el usuario escribe a mano, no va a repetir capitalización.
    expect(sportColor(' Pádel ')).toBe(sportColor('pádel'))
  })

  it('textos distintos caen en colores distintos', () => {
    const free = ['pádel', 'Bicicleta trabajo', 'running', 'escalada']
    // Lambda y no `free.map(sportColor)`: map pasa el índice como 2º argumento
    // y ahí va ahora el mapa de colores del usuario.
    expect(new Set(free.map((s) => sportColor(s))).size).toBe(free.length)
  })

  it('el color elegido por el usuario gana al fijo y al hash', () => {
    expect(sportColor('fuerza', { fuerza: '#ff0000' })).toBe('#ff0000')
    expect(sportColor('pádel', { 'pádel': '#00ff00' })).toBe('#00ff00')
  })

  it('sin color elegido para ESE deporte, sigue el comportamiento de siempre', () => {
    expect(sportColor('fuerza', { otro: '#ff0000' })).toBe(SPORT.fuerza)
    expect(sportColor('pádel', {})).toBe(sportColor('pádel'))
  })
})

describe('groupByDay', () => {
  // 00:30 y 01:45 del 6-jul locales (Madrid, UTC+2) + uno del día siguiente.
  // De madrugada a propósito: en UTC esos dos caerían en el día 5.
  const workouts = [
    { id: 1, start_ts: 1783290600 },
    { id: 2, start_ts: 1783295100 },
    { id: 3, start_ts: 1783400000 },
  ] as Workout[]

  it('agrupa por día LOCAL, no por el día UTC del timestamp', () => {
    expect(groupByDay(workouts).map((d) => [d.day, d.workouts.length])).toEqual([
      ['2026-07-06', 2],
      ['2026-07-07', 1],
    ])
  })
})

describe('effectiveFilter', () => {
  it('respeta el filtro cuando ese tipo está presente en el rango', () => {
    expect(effectiveFilter('fuerza', ['fuerza', 'voley_playa'])).toBe('fuerza')
  })

  it('cae a "all" cuando el tipo elegido no existe en el rango visible', () => {
    // Mes con "otro" -> semana sin ninguno: antes la lista salía vacía y las
    // pastillas no se pintaban (solo aparecen con >1 tipo), así que no había
    // forma de deshacer el filtro.
    expect(effectiveFilter('otro', ['fuerza'])).toBe('all')
  })

  it('"all" se queda como está aunque el rango esté vacío', () => {
    expect(effectiveFilter('all', [])).toBe('all')
  })

  it('trata "Sin clasificar" (null) como un tipo más', () => {
    expect(effectiveFilter(null, [null, 'fuerza'])).toBe(null)
    expect(effectiveFilter(null, ['fuerza'])).toBe('all')
  })
})

describe('sessionVolume', () => {
  const set = (reps: number | null, weight: number | null, type = 'normal') => ({
    set_index: 0,
    reps,
    weight_kg: weight,
    rpe: null,
    set_type: type,
  })

  it('suma peso por repeticiones de cada serie', () => {
    const exercises = [{ exercise: 'Press', muscle_group: null, sets: [set(10, 50), set(8, 60)] }]
    expect(sessionVolume(exercises)).toBe(980)
  })

  it('no cuenta el calentamiento: no es volumen de trabajo', () => {
    const exercises = [{ exercise: 'Press', muscle_group: null, sets: [set(10, 50), set(20, 20, 'warmup')] }]
    expect(sessionVolume(exercises)).toBe(500)
  })

  it('una serie sin peso o sin reps no aporta, pero tampoco rompe', () => {
    const exercises = [{ exercise: 'Dominadas', muscle_group: null, sets: [set(8, null), set(null, 40)] }]
    expect(sessionVolume(exercises)).toBe(0)
  })

  it('sin ejercicios no hay volumen que enseñar', () => {
    expect(sessionVolume(undefined)).toBeNull()
    expect(sessionVolume([])).toBeNull()
  })
})

describe('suggestedSports', () => {
  const sports = [
    { name: 'voley_playa' },
    { name: 'auto_ia' },
    { name: 'Bicicleta trabajo' },
    { name: 'otro' },
    { name: 'Andar' },
  ]

  it('deja fuera los cubos genéricos', () => {
    // "Actividad detectada" es de lo que estás saliendo al clasificar.
    expect(suggestedSports(sports).map((s) => s.name)).not.toContain('auto_ia')
    expect(suggestedSports(sports).map((s) => s.name)).not.toContain('otro')
  })

  it('ordena alfabéticamente para poder buscar con la vista', () => {
    expect(suggestedSports(sports).map((s) => s.name)).toEqual([
      'Andar',
      'Bicicleta trabajo',
      'voley_playa',
    ])
  })

  it('no toca el array del llamante', () => {
    const original = [...sports]
    suggestedSports(sports)
    expect(sports).toEqual(original)
  })
})
