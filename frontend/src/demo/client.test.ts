import { describe, expect, it } from 'vitest'
import { createClient, toResponse, type WorkerRequest } from './client'

function setup() {
  const sent: WorkerRequest[] = []
  const client = createClient((req) => sent.push(req))
  return { sent, ...client }
}

describe('createClient', () => {
  it('manda método, url y cuerpo, con un id distinto por petición', () => {
    const { sent, request } = setup()
    void request('/api/overview')
    void request('/api/annotations', { method: 'POST', body: '{"text":"x"}' })
    expect(sent).toEqual([
      { id: 0, method: 'GET', url: '/api/overview', body: null },
      { id: 1, method: 'POST', url: '/api/annotations', body: '{"text":"x"}' },
    ])
  })

  it('cada respuesta resuelve SU petición aunque lleguen en otro orden', async () => {
    const { request, receive } = setup()
    const a = request('/api/a')
    const b = request('/api/b')
    receive({ id: 1, status: 200, content_type: 'application/json', body: '"b"' })
    receive({ id: 0, status: 404, content_type: 'application/json', body: '{"detail":"no"}' })
    expect(await (await b).json()).toBe('b')
    const resA = await a
    expect(resA.status).toBe(404)
    expect(resA.ok).toBe(false)
    expect(await resA.json()).toEqual({ detail: 'no' })
  })

  it('abortar rechaza con AbortError y la respuesta tardía se ignora', async () => {
    const { request, receive } = setup()
    const controller = new AbortController()
    const pending = request('/api/a', { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    receive({ id: 0, status: 200, content_type: 'application/json', body: '1' }) // no revienta
    await expect(request('/api/b', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('toResponse', () => {
  it('lleva estado, content-type y cuerpo', async () => {
    const res = toResponse({ status: 201, content_type: 'application/json', body: '{"id":3}' })
    expect(res.status).toBe(201)
    expect(res.headers.get('content-type')).toBe('application/json')
    expect(await res.json()).toEqual({ id: 3 })
  })

  it('un 204 sale sin cuerpo (con cuerpo, Response lanza)', async () => {
    const res = toResponse({ status: 204, content_type: '', body: '' })
    expect(res.status).toBe(204)
    expect(res.body).toBeNull()
  })
})
