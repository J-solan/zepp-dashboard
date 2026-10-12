/** Tema de la app: 'auto' sigue al sistema; 'light'/'dark' lo fuerzan.
 *
 * Los colores no viven aquí: cada token de `index.css` es `light-dark(claro,
 * oscuro)` y los elige `color-scheme`, que a su vez depende de
 * `data-theme` en <html>. Este módulo solo decide ese atributo y lo recuerda.
 * El script en línea de `index.html` lo aplica antes del primer pintado (con
 * la misma clave) para que un tema forzado no parpadee en claro al cargar. */

export type Theme = 'auto' | 'light' | 'dark'

export const THEME_KEY = 'zepp-dashboard:theme'

const ORDER: Theme[] = ['auto', 'light', 'dark']

export const nextTheme = (theme: Theme): Theme => ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]

export function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'auto'
  } catch {
    return 'auto' // modo privado o almacenamiento bloqueado
  }
}

export function saveTheme(theme: Theme): void {
  try {
    if (theme === 'auto') localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, theme)
  } catch {
    // Sin almacenamiento el tema dura lo que la pestaña abierta.
  }
}

/** Fija el tema en el DOM: `data-theme` en <html> y el color de la barra del
 * navegador/PWA. Las dos `<meta name="theme-color">` de `index.html` llevan su
 * `media` del sistema; forzado, la del tema elegido pasa a `all` y la otra a
 * `not all`. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'auto') delete root.dataset.theme
  else root.dataset.theme = theme

  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"][data-scheme]')) {
    const scheme = meta.dataset.scheme
    meta.media = theme === 'auto' ? `(prefers-color-scheme: ${scheme})` : theme === scheme ? 'all' : 'not all'
  }
}
