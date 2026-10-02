// Service worker a mano, sin Workbox: la lógica real son dos estrategias y
// veinte líneas. Una dependencia de build aquí costaría más de lo que ahorra.
//
// - App shell — JS/CSS/iconos (hash en el nombre): CACHE FIRST. Un despliegue
//   nuevo trae URLs nuevas, así que nunca sirve una versión vieja por error.
// - App shell — HTML de navegación: NETWORK FIRST, cae al index cacheado
//   (SPA de una sola página). Mismo motivo que `/api/*` abajo.
// - `/api/*`: NETWORK FIRST con copia en caché. Online mandan los datos
//   frescos; sin red se sirve lo último visto, que es justo lo que se espera
//   al abrir la app en el metro.
//
// Lo que NO cachea: las peticiones que no son GET. Un POST /api/sync o un
// PATCH tienen que fallar de verdad si no hay red — fingir que se guardaron
// sería mentir sobre datos del usuario.

const VERSION = 'helio-v1'
const SHELL = `${VERSION}-shell`
const DATA = `${VERSION}-data`

// cache.addAll() es todo-o-nada: si un solo icono da 404 o hay un corte de
// red a mitad de instalación, la instalación entera aborta. cache.add() por
// URL con catch individual deja que el resto se precachee igual.
async function precacheOne(cache, url) {
  try {
    await cache.add(url)
  } catch {
    // se reintentará en la siguiente instalación; no debe tirar abajo el resto
  }
}

/** Precachea el index Y los bundles que referencia.
 *
 * Los nombres de `/assets/` llevan hash y solo se conocen tras el build, así
 * que no se pueden escribir aquí. Dejarlos al cacheo en tiempo de ejecución NO
 * vale: si el navegador los sirvió de su propia caché HTTP antes de que el SW
 * tomara el control, nunca pasan por aquí, y la primera carga sin red da una
 * página EN BLANCO (index cacheado, JS ausente). Comprobado.
 *
 * Leer el HTML y sacar sus `src`/`href` resuelve el hash sin build step ni
 * dependencia, y se re-resuelve solo en cada despliegue.
 */
async function precacheShell() {
  const cache = await caches.open(SHELL)
  const core = ['/', '/manifest.webmanifest', '/icon.svg', '/icon-maskable.svg', '/apple-touch-icon.png']
  await Promise.all(core.map((url) => precacheOne(cache, url)))
  const index = await cache.match('/')
  if (!index) return
  const html = await index.text()
  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])
  await Promise.all(assets.map((url) => precacheOne(cache, url)))
}

self.addEventListener('install', (event) => {
  event.waitUntil(precacheShell())
  self.skipWaiting()
})

// Al activar una versión nueva se tiran las cachés de las anteriores, o el
// disco crecería sin límite con cada despliegue.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

async function networkFirst(request) {
  try {
    const response = await fetch(request)
    if (response.ok) (await caches.open(DATA)).put(request, response.clone())
    return response
  } catch (err) {
    const cached = await caches.match(request)
    if (cached) return cached
    throw err
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) (await caches.open(SHELL)).put(request, response.clone())
  return response
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request))
  } else if (request.mode === 'navigate') {
    // Navegación offline: la app es una SPA de una sola página, así que
    // cualquier ruta se resuelve con el index cacheado.
    event.respondWith(networkFirst(request).catch(() => caches.match('/')))
  } else {
    event.respondWith(cacheFirst(request))
  }
})
