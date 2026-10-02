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
