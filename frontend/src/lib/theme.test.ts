import { afterEach, describe, expect, it, vi } from 'vitest'
import { THEME_KEY, loadTheme, nextTheme, saveTheme } from './theme'

function fakeStorage(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => void (data[k] = v),
    removeItem: (k: string) => void delete data[k],
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('nextTheme', () => {
  it('cicla auto -> claro -> oscuro -> auto', () => {
    expect(nextTheme('auto')).toBe('light')
    expect(nextTheme('light')).toBe('dark')
    expect(nextTheme('dark')).toBe('auto')
  })
})

describe('loadTheme / saveTheme', () => {
  it('sin nada guardado, o con basura, es auto', () => {
    vi.stubGlobal('localStorage', fakeStorage())
    expect(loadTheme()).toBe('auto')
    vi.stubGlobal('localStorage', fakeStorage({ [THEME_KEY]: 'sepia' }))
    expect(loadTheme()).toBe('auto')
  })

  it('guarda claro/oscuro y auto borra la clave', () => {
    const storage = fakeStorage()
    vi.stubGlobal('localStorage', storage)
    saveTheme('dark')
    expect(loadTheme()).toBe('dark')
    saveTheme('auto')
    expect(storage.data).toEqual({})
    expect(loadTheme()).toBe('auto')
  })

  it('con el almacenamiento bloqueado no rompe: auto y no lanza', () => {
    const blocked = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('SecurityError')
      },
      removeItem: () => {
        throw new Error('SecurityError')
      },
    }
    vi.stubGlobal('localStorage', blocked)
    expect(loadTheme()).toBe('auto')
    expect(() => saveTheme('dark')).not.toThrow()
  })
})
