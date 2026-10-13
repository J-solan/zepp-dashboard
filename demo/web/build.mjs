// Completa un `frontend/dist` compilado en modo demo para GitHub Pages: le
// añade Pyodide y el backend de Python, que corren en el navegador del
// visitante (ver demo/browser.py). Todo se sirve desde el propio Pages: en
// ejecución no se llama a ningún tercero.
//
//   node build.mjs <distDir> [ref]     # ref de git, por defecto HEAD
//
// El código Python sale de `git archive <ref>`: solo lo commiteado, nunca un
// fichero sin trackear (config.toml, data/, fixtures_local/...).

import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../..')
if (!process.argv[2]) throw new Error('uso: node build.mjs <distDir> [ref]')
const dist = resolve(process.argv[2])
const ref = process.argv[3] ?? 'HEAD'
if (!existsSync(join(dist, 'index.html'))) throw new Error(`${dist} no tiene index.html: compila antes el frontend`)

const npmDir = join(here, 'node_modules', 'pyodide')
const version = JSON.parse(readFileSync(join(npmDir, 'package.json'), 'utf8')).version
const lock = JSON.parse(readFileSync(join(npmDir, 'pyodide-lock.json'), 'utf8'))

// Lo que importa el backend, con sus dependencias según el lock. Menos:
// - `httpx` y `cryptography`: solo hablan con Zepp, y demo/browser.py los
//   sustituye por módulos vacíos (el `fastapi` de Pyodide trae `httpx`).
// - `jinja2`: solo para las plantillas de FastAPI, que no se usan.
const ROOTS = ['fastapi', 'tzdata']
const UNUSED = ['httpx', 'jinja2', 'cryptography']
const canon = (name) => name.toLowerCase().replace(/[-_.]+/g, '-')
const packages = []
const pending = [...ROOTS]
while (pending.length) {
  const name = canon(pending.pop())
  if (packages.includes(name) || UNUSED.includes(name)) continue
  if (!lock.packages[name]) throw new Error(`${name} no está en pyodide-lock.json`)
  packages.push(name)
  pending.push(...lock.packages[name].depends)
}
packages.sort()

// --- Pyodide: núcleo del paquete npm + wheels verificadas contra el lock ---
const outPy = join(dist, 'pyodide')
mkdirSync(outPy, { recursive: true })
for (const file of ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip']) {
  copyFileSync(join(npmDir, file), join(outPy, file))
}
// El lock, solo con lo que se publica: `loadPackage` resuelve dependencias con
// él, así que sin esto volvería a pedir lo de UNUSED (y pesa 116 KB contra 4).
lock.packages = Object.fromEntries(packages.map((name) => {
  const entry = lock.packages[name]
  return [name, { ...entry, depends: entry.depends.filter((dep) => packages.includes(canon(dep))) }]
}))
writeFileSync(join(outPy, 'pyodide-lock.json'), JSON.stringify(lock))
await Promise.all(packages.map(async (name) => {
  const { file_name: file, sha256 } = lock.packages[name]
  const url = `https://cdn.jsdelivr.net/pyodide/v${version}/full/${file}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`)
  const bytes = Buffer.from(await res.arrayBuffer())
  const got = createHash('sha256').update(bytes).digest('hex')
  if (got !== sha256) throw new Error(`${file}: sha256 ${got}, el lock dice ${sha256}`)
  writeFileSync(join(outPy, file), bytes)
}))

// Se redistribuye Pyodide (MPL-2.0) y el paquete npm no trae el texto de la
// licencia: el aviso dice cuál es y dónde está el código fuente.
writeFileSync(join(outPy, 'NOTICE.txt'), [
  `Pyodide ${version}: Mozilla Public License 2.0, https://mozilla.org/MPL/2.0/`,
  `Source code: https://github.com/pyodide/pyodide/tree/${version}`,
  `Packages: ${packages.join(', ')}. Each wheel carries its own license in its metadata.`,
  '',
].join('\n'))

// --- Código de la app (sin tests ni este directorio) ---
const outApp = join(dist, 'py')
mkdirSync(outApp, { recursive: true })
execFileSync('git', ['archive', '--format=zip', `--output=${join(outApp, 'app.zip')}`, ref, '--',
  'backend', 'ingest', 'demo', 'db', 'pyproject.toml', ':(exclude)*/tests/*', ':(exclude)demo/web'], { cwd: repo })
writeFileSync(join(outApp, 'manifest.json'), JSON.stringify({ pyodide: version, packages, app: 'app.zip' }, null, 2) + '\n')

// --- Tamaños ---
const kb = (bytes) => `${(bytes / 1024).toFixed(0).padStart(6)} KB`
let total = 0
for (const dir of [outPy, outApp]) {
  for (const file of readdirSync(dir).sort()) {
    const size = statSync(join(dir, file)).size
    total += size
    if (size > 50 * 1024) console.log(`${kb(size)}  ${dir === outPy ? 'pyodide' : 'py'}/${file}`)
  }
}
console.log(`${kb(total)}  total añadido; ${packages.length} paquetes: ${packages.join(', ')}`)
