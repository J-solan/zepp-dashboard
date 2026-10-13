// Arranque del modo demo: el backend de Python en un Worker y, mientras
// arranca, una pantalla que cuenta qué está pasando. Solo se importa desde
// ramas `import.meta.env.VITE_DEMO_WASM === '1'`, así que la compilación
// normal no lleva ni esto ni el Worker.
import { createRoot } from 'react-dom/client'
import { BootScreen, type BootState } from './BootScreen'
import { createClient, type WorkerMessage } from './client'

// Se crea al importar el módulo, antes de montar React, para que la descarga
// de Python empiece cuanto antes.
const worker = new Worker(new URL('./pyodide.worker.ts', import.meta.url), { type: 'module' })
const client = createClient((req) => worker.postMessage(req))

/** `fetch` contra el backend del Worker. Lo usa `apiFetch` en modo demo. */
export const wasmFetch = client.request

let state: BootState = { step: 'python', ready: false, error: null }
let onChange: (s: BootState) => void = () => {}

function update(patch: Partial<BootState>): void {
  state = { ...state, ...patch }
  onChange(state)
}

worker.addEventListener('message', (event: MessageEvent<WorkerMessage>) => {
  const msg = event.data
  if (msg.type === 'response') client.receive(msg)
  else if (msg.type === 'step') update({ step: msg.step })
  else if (msg.type === 'ready') update({ ready: true })
  else update({ error: msg.message })
})
// Sin respuesta del Worker ni de Python: el script no se pudo cargar
// (navegador sin Workers de módulo, red caída...).
worker.addEventListener('error', () => update({ error: 'No se pudo cargar el Worker de la demo.' }))

/** Pinta la pantalla de carga en `el` y resuelve cuando el backend ya
 * responde. Si falla, se queda en el error con el botón de reintentar. */
export function bootDemo(el: HTMLElement): Promise<void> {
  // En un hijo, no en `el`: el primer render de la app en `el` borra lo que
  // haya dentro, así que la pantalla de carga sigue a la vista hasta ese mismo
  // instante, sin parpadeo en blanco entre una y otra.
  const root = createRoot(el.appendChild(document.createElement('div')))
  return new Promise((resolve) => {
    onChange = (s) => (s.ready ? resolve() : root.render(<BootScreen {...s} />))
    onChange(state)
  })
}
