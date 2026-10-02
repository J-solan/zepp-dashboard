import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, authRequired, fetchJson, setToken } from './api'

/** localStorage en memoria: vitest corre en Node, sin DOM. */
function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => {
      data.delete(key)
    },
    setItem: (key, value) => {
      data.set(key, String(value))
    },
  }
}

const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage())
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => new Response('{}', { status: 200 }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function sentHeaders(): Headers {
  return new Headers(fetchMock.mock.calls[0][1]?.headers)
}

describe('apiFetch', () => {
  it('sin token guardado no manda Authorization', async () => {
    await apiFetch('/api/hr')
    expect(sentHeaders().get('Authorization')).toBeNull()
  })

  it('con token guardado lo manda como Bearer', async () => {
    setToken('s3cret')
    await apiFetch('/api/hr')
    expect(sentHeaders().get('Authorization')).toBe('Bearer s3cret')
  })

  it('conserva el método, el cuerpo y las cabeceras de la petición', async () => {
    setToken('s3cret')
    await apiFetch('/api/annotations', {
      method: 'POST',
      body: '{}',
      headers: { 'Content-Type': 'application/json' },
    })
    const init = fetchMock.mock.calls[0][1]
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe('{}')
    expect(sentHeaders().get('Content-Type')).toBe('application/json')
  })

  it('un 401 avisa a quien escuche authRequired', async () => {
    fetchMock.mockImplementationOnce(async () => new Response(null, { status: 401 }))
    const listener = vi.fn()
    authRequired.addEventListener('required', listener)
    try {
      const res = await apiFetch('/api/hr')
      expect(res.status).toBe(401)
      expect(listener).toHaveBeenCalledOnce()
    } finally {
      authRequired.removeEventListener('required', listener)
    }
  })

  it('sin almacenamiento (modo privado) sigue funcionando, sin token', async () => {
    const blocked = () => {
      throw new Error('SecurityError')
    }
    vi.stubGlobal('localStorage', { getItem: blocked, setItem: blocked })
    setToken('s3cret')
    await apiFetch('/api/hr')
    expect(sentHeaders().get('Authorization')).toBeNull()
  })
})

describe('fetchJson', () => {
  it('pasa por apiFetch: también lleva el token', async () => {
    setToken('s3cret')
    await fetchJson('/api/hr')
    expect(sentHeaders().get('Authorization')).toBe('Bearer s3cret')
  })

  it('convierte un 401 en Error con el detail del backend', async () => {
    fetchMock.mockImplementationOnce(
      async () => new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }),
    )
    await expect(fetchJson('/api/hr')).rejects.toThrow('unauthorized')
  })
})
