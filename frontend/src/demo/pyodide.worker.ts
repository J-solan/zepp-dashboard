// El backend de verdad (FastAPI + SQLite) corriendo en el navegador con
// Pyodide. Va en un Worker para que arrancar Python y generar los datos no
// congelen la página. Python, sus paquetes y el código del backend se sirven
// junto a la web (`pyodide/` y `py/`), sin CDN de por medio.
import type { RawResponse, WorkerMessage, WorkerRequest } from './client'

// Lo poco que se usa de Pyodide y de `demo/browser.py`, sin depender de sus tipos.
interface PyProxy<T> {
  toJs(options: { dict_converter: typeof Object.fromEntries }): T
  destroy(): void
}
interface DemoBackend {
  boot(): Promise<void>
  handle(method: string, url: string, body: string | null): Promise<PyProxy<RawResponse>>
}
interface Pyodide {
  loadPackage(names: string[], options: { messageCallback: (msg: string) => void }): Promise<void>
  unpackArchive(buffer: ArrayBuffer, format: string, options: { extractDir: string }): void
  runPython(code: string): unknown
  pyimport(name: string): DemoBackend
}

const BASE = import.meta.env.BASE_URL

const send = (msg: WorkerMessage) => postMessage(msg)

// Una excepción de Python trae el traceback entero; para la pantalla basta la
// última línea (`ValueError: ...`). El traceback completo va a la consola.
function lastLine(err: unknown): string {
  console.error(err)
  const text = String(err instanceof Error ? err.message : err).trim()
  return text.slice(text.lastIndexOf('\n') + 1)
}

async function get(path: string): Promise<Response> {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`No se pudo descargar ${path} (${res.status})`)
  return res
}

async function boot(): Promise<DemoBackend> {
  send({ type: 'step', step: 'python' })
  // El manifiesto baja a la vez que Python, no detrás.
  const [py, manifest] = await Promise.all([
    import(/* @vite-ignore */ `${BASE}pyodide/pyodide.mjs`).then(
      ({ loadPyodide }) => loadPyodide({ indexURL: `${BASE}pyodide/` }) as Promise<Pyodide>,
    ),
    get('py/manifest.json').then((r) => r.json() as Promise<{ packages: string[]; app: string }>),
  ])

  send({ type: 'step', step: 'packages' })
  const [, app] = await Promise.all([
    // Sin messageCallback, Pyodide anuncia cada paquete en la consola.
    py.loadPackage(manifest.packages, { messageCallback: () => {} }),
    get(`py/${manifest.app}`).then((r) => r.arrayBuffer()),
  ])

  send({ type: 'step', step: 'backend' })
  py.unpackArchive(app, 'zip', { extractDir: '/app' })
  py.runPython("import sys; sys.path.insert(0, '/app')")
  const backend = py.pyimport('demo.browser')

  send({ type: 'step', step: 'seed' })
  await backend.boot()
  return backend
}

const ready = boot()
ready.then(
  () => send({ type: 'ready' }),
  (err) => send({ type: 'failed', message: lastLine(err) }),
)

// La cola: cada petición espera a la anterior y todas a que el backend haya
// arrancado. Una a una, además, una escritura y la lectura que la sigue se
// atienden en el orden en que se pidieron.
let queue: Promise<void> = Promise.resolve()

addEventListener('message', (event: MessageEvent<WorkerRequest>) => {
  const { id, method, url, body } = event.data
  queue = queue.then(async () => {
    let res: RawResponse
    try {
      const proxy = await (await ready).handle(method, url, body)
      try {
        res = proxy.toJs({ dict_converter: Object.fromEntries })
      } finally {
        proxy.destroy()
      }
    } catch (err) {
      // `{detail}` es lo que fetchJson enseña como mensaje de error.
      res = { status: 500, content_type: 'application/json', body: JSON.stringify({ detail: lastLine(err) }) }
    }
    send({ type: 'response', id, ...res })
  })
})
