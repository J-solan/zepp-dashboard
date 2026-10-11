import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Solo los pesos que se usan y solo el subconjunto latino: el resto sería
// peso muerto en el precacheado del service worker.
import '@fontsource/newsreader/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import './index.css'
import App from './App.tsx'
import { fetchJson } from './lib/api'
import { setAppTz } from './lib/date'
import type { Overview } from './lib/types'

// "Hoy", las medianoches y las horas se calculan en la zona del backend, y App
// ya las usa en su primer render (el rango por defecto): se pide antes de pintar.
// Si no llega (sin red ni copia en caché, 401 sin token, zona desconocida...) se
// queda la del navegador; el timeout evita una pantalla en blanco indefinida con
// mala red. Tras guardar el token, TokenGate recarga y esto se repite ya con él.
try {
  const { tz } = await fetchJson<Overview>('/api/overview', { signal: AbortSignal.timeout(5000) })
  setAppTz(tz)
} catch {
  // zona del navegador, el valor por defecto de lib/date
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Service worker solo en producción: en `npm run dev` se quedaría sirviendo
// módulos cacheados y romperías el hot-reload preguntándote por qué no se
// aplica lo que acabas de escribir.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Sin service worker la app funciona igual, solo pierde el offline.
    })
  })
}
