// Prueba de humo de lo que deja build.mjs: arranca Pyodide desde <distDir>
// con la misma secuencia que el Worker de la web y recorre la API que usa.
//
//   node smoke.mjs <distDir>
//
// Sale con código != 0 si algo no responde 2xx (salvo /api/sync, que en la
// demo es un 503).

import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

if (!process.argv[2]) throw new Error('uso: node smoke.mjs <distDir>')
const dist = resolve(process.argv[2])
const t0 = performance.now()
let last = t0
const lap = (label) => {
  const now = performance.now()
  console.log(`${((now - last) / 1000).toFixed(2).padStart(6)} s  ${label}`)
  last = now
}
// En Node, Pyodide descarga del CDN lo que no encuentre en indexURL y lo deja
// ahí: el humo pasaría y en el navegador sería un 404. Si dist cambia, falla.
const pyodideDir = join(dist, 'pyodide')
const before = readdirSync(pyodideDir).join()
const bytes = (path) => new Uint8Array(readFileSync(join(dist, path)))

// --- La secuencia del Worker (con fs en vez de fetch) ---
const { loadPyodide } = await import(pathToFileURL(join(pyodideDir, 'pyodide.mjs')).href)
const py = await loadPyodide({ indexURL: `${pyodideDir}/` })
lap('loadPyodide')
const manifest = JSON.parse(readFileSync(join(dist, 'py', 'manifest.json'), 'utf8'))
await py.loadPackage(manifest.packages, { messageCallback: () => {} })
lap(`loadPackage (${manifest.packages.length})`)
py.unpackArchive(bytes(`py/${manifest.app}`), 'zip', { extractDir: '/app' })
py.runPython("import sys; sys.path.insert(0, '/app')")
const browser = py.pyimport('demo.browser')
lap('app descomprimida e importada')
await browser.boot()
lap('boot (imports del backend + semilla de 90 días)')
const handle = async (method, url, body) =>
  (await browser.handle(method, url, body)).toJs({ dict_converter: Object.fromEntries })

// --- Lo que pide la web ---
const failures = []
const check = async (method, url, body, expected = (s) => s >= 200 && s < 300) => {
  const t = performance.now()
  const res = await handle(method, url, body)
  const ok = expected(res.status)
  if (!ok) failures.push(`${method} ${url} -> ${res.status} ${res.body.slice(0, 200)}`)
  console.log(`${ok ? 'ok ' : 'MAL'} ${res.status} ${String(Math.round(performance.now() - t)).padStart(4)} ms ${String(res.body.length).padStart(8)} B  ${method} ${url}`)
  return res.body ? JSON.parse(res.body) : null
}
const today = (await check('GET', '/api/overview')).date
const ago = (n) => {
  const d = new Date(`${today}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() - n)
  return d.toISOString().slice(0, 10)
}
for (const days of [1, 7, 30, 90]) {
  const range = `from=${ago(days - 1)}&to=${today}`
  for (const path of ['daily', 'sleep', 'workouts', 'hr', 'stress', 'biocharge', 'annotations', 'muscles/volume']) {
    await check('GET', `/api/${path}?${range}`)
  }
}
await check('GET', `/api/stress?from=${today}&to=${today}&bucket=900`)
await check('GET', `/api/workouts?from=${ago(89)}&to=${today}&include_ignored=true`)
await check('GET', '/api/sports')
await check('GET', '/api/sync/status')
const pending = await check('GET', '/api/workouts/pending')

// --- Escrituras ---
await check('POST', `/api/workouts/${pending[0].id}/review`, JSON.stringify({ action: 'ignore' }))
if ((await check('GET', '/api/workouts/pending')).length !== pending.length - 1) failures.push('la cola no bajó tras ignorar')
await check('PUT', `/api/sports/${encodeURIComponent('vóley playa')}`, JSON.stringify({ color: '#336699' }))
const note = await check('POST', '/api/annotations', JSON.stringify({ start_ts: 1, end_ts: 2, text: 'humo' }))
await check('DELETE', `/api/annotations/${note.id}`)
await check('POST', '/api/sync', undefined, (s) => s === 503)
lap('API recorrida')

if (readdirSync(pyodideDir).join() !== before) failures.push(`${pyodideDir} cambió: falta algo en el build`)
console.log(`${((performance.now() - t0) / 1000).toFixed(2).padStart(6)} s  total`)
if (failures.length) {
  console.error(`\n${failures.length} fallos:\n${failures.join('\n')}`)
  process.exit(1)
}
