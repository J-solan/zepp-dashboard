// Estampa VERSION en dist/sw.js con un hash de dist/index.html.
//
// Sin esto, sw.js sale del build con bytes IDÉNTICOS en cada deploy (solo
// index.html y los nombres hasheados de /assets/ cambian), y el navegador
// decide si hay worker nuevo comparando bytes de sw.js: nunca detecta el
// deploy, precacheShell() no vuelve a correr, y la caché SHELL no se limpia
// nunca. Hashear index.html (que sí cambia cuando cambian los assets) basta:
// mismo contenido -> mismo hash -> no hace falta reinstalar.
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const html = readFileSync(join(dist, 'index.html'), 'utf8')
const hash = createHash('sha256').update(html).digest('hex').slice(0, 10)

const swPath = join(dist, 'sw.js')
const sw = readFileSync(swPath, 'utf8')
const pattern = /const VERSION = '[^']*'/
if (!pattern.test(sw)) throw new Error('sw.js: no se encontró la línea VERSION a reemplazar')
writeFileSync(swPath, sw.replace(pattern, `const VERSION = 'helio-${hash}'`))
