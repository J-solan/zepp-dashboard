import { useEffect, useState } from 'react'
import { type Theme, applyTheme, loadTheme, nextTheme, saveTheme } from '../lib/theme'
import { MoonIcon, SunIcon, ThemeAutoIcon } from './icons'

const LABEL: Record<Theme, string> = { auto: 'automático', light: 'claro', dark: 'oscuro' }
const ICON = { auto: ThemeAutoIcon, light: SunIcon, dark: MoonIcon }

/** Cicla Auto -> Claro -> Oscuro. El icono muestra el tema ACTUAL; la etiqueta
 * accesible dice también a cuál pasa al pulsar. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(loadTheme)
  useEffect(() => applyTheme(theme), [theme])

  const next = nextTheme(theme)
  const Icon = ICON[theme]
  return (
    <button
      type="button"
      onClick={() => {
        saveTheme(next)
        setTheme(next)
      }}
      title={`Tema: ${LABEL[theme]}`}
      aria-label={`Tema: ${LABEL[theme]}. Cambiar a ${LABEL[next]}`}
      className="self-center rounded-card p-1 text-ink-secondary transition-colors hover:text-ink
                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <Icon className="size-4" />
    </button>
  )
}
