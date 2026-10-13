// Protocolo entre la página y el Worker de Pyodide (modo demo). Lógica pura,
// sin Worker: lo que lo crea y lo engancha está en boot.tsx.

/** Pasos del arranque, en orden. El Worker avisa al empezar cada uno. */
export const STEPS = {
  python: 'Descargando Python',
  packages: 'Cargando paquetes',
  backend: 'Cargando el backend',
  seed: 'Generando 90 días de datos inventados',
} as const
export type Step = keyof typeof STEPS

/** Lo que devuelve `demo.browser.handle()` en Python. */
export interface RawResponse {
  status: number
  content_type: string
  body: string
}

export interface WorkerRequest {
  id: number
  method: string
  url: string
  body: string | null
}

export type WorkerMessage =
  | { type: 'step'; step: Step }
  | { type: 'ready' }
  | { type: 'failed'; message: string }
  | ({ type: 'response'; id: number } & RawResponse)

/** Un `Response` de verdad: así `fetchJson` (errores, 401, JSON) no distingue
 * el backend del Worker del de la red. */
export function toResponse({ status, content_type, body }: RawResponse): Response {
  // Con estos estados `new Response(cuerpo)` lanza, aunque el cuerpo sea ''.
  const nullBody = status === 204 || status === 205 || status === 304
  return new Response(nullBody ? null : body, { status, headers: { 'content-type': content_type } })
}

/** Lado página: numera cada petición y resuelve su promesa cuando vuelve la
 * respuesta con el mismo id. La cola hasta que Python arranca la lleva el
 * Worker; aquí solo se espera. */
export function createClient(post: (req: WorkerRequest) => void) {
  let nextId = 0
  const pending = new Map<number, (raw: RawResponse) => void>()

  function request(url: string, init: RequestInit = {}): Promise<Response> {
    const { signal } = init
    // Mismo contrato que fetch: abortar rechaza con el motivo del signal
    // (AbortError), y useApi cuenta con ello para descartar respuestas viejas.
    if (signal?.aborted) return Promise.reject(signal.reason)
    return new Promise((resolve, reject) => {
      const id = nextId++
      pending.set(id, (raw) => resolve(toResponse(raw)))
      signal?.addEventListener(
        'abort',
        () => {
          pending.delete(id) // el Worker la contestará igual; se ignora
          reject(signal.reason)
        },
        { once: true },
      )
      // La app solo manda cuerpos JSON ya serializados (texto).
      post({ id, method: init.method ?? 'GET', url, body: (init.body as string | undefined) ?? null })
    })
  }

  function receive(msg: { id: number } & RawResponse): void {
    pending.get(msg.id)?.(msg)
    pending.delete(msg.id)
  }

  return { request, receive }
}
