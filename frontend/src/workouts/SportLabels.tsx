import { useState } from 'react'
import { Button } from '../components/Button'
import { TrashIcon } from '../components/icons'
import { useSports } from '../hooks/useSports'
import { sportColor, sportLabel } from '../lib/workouts'

/** `var(--color-x)` -> el hex real que hay detrás.
 *
 * `<input type="color">` SOLO acepta `#rrggbb`: con cualquier otra cosa el
 * navegador no avisa, se queda en negro. Y la paleta de la app son custom
 * properties de `index.css`, así que hay que resolverlas contra el DOM. */
function toHex(color: string): string {
  const variable = color.match(/^var\((--[\w-]+)\)$/)
  if (!variable) return color
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable[1]).trim()
  return /^#[0-9a-f]{6}$/i.test(value) ? value : '#888888'
}

/** Gestión de etiquetas: crear una a mano y elegirle color.
 *
 * `<input type="color">` es el selector nativo del sistema — sin dependencias,
 * sin rueda de color propia que mantener, y en móvil sale el picker del SO.
 *
 * Una etiqueta EN USO no se puede borrar del todo: `DELETE /api/sports/{name}`
 * solo quita el color, porque los entrenos que la tengan escrita la siguen
 * teniendo. Borrar una etiqueta no puede reclasificar entrenos por la puerta de
 * atrás; para eso se edita el entreno.
 */
export function SportLabels() {
  const { sports, styles, save, remove } = useSports()
  const [nuevo, setNuevo] = useState('')
  const [error, setError] = useState<string | null>(null)

  const crear = async () => {
    const name = nuevo.trim()
    if (!name) return
    setError(null)
    try {
      await save(name, null)
      setNuevo('')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        {sports.map((sport) => (
          <div key={sport.name} className="flex items-center gap-2">
            <input
              type="color"
              aria-label={`Color de ${sportLabel(sport.name)}`}
              value={toHex(sportColor(sport.name, styles))}
              onChange={(e) => save(sport.name, e.target.value)}
              className="h-7 w-9 shrink-0 cursor-pointer rounded border border-hairline bg-transparent"
            />
            <span
              className="min-w-0 flex-1 truncate rounded-full px-2 py-0.5 text-label uppercase"
              style={{
                backgroundColor: `color-mix(in oklab, ${sportColor(sport.name, styles)} 12%, transparent)`,
                color: sportColor(sport.name, styles),
              }}
            >
              {sportLabel(sport.name)}
            </span>
            {/* Solo se ofrece quitar el color a las que lo tienen puesto: en las
                demás el botón no haría nada visible. */}
            {sport.color && (
              <button
                onClick={() => remove(sport.name)}
                aria-label={`Quitar el color de ${sportLabel(sport.name)}`}
                title="Quitar el color"
                className="shrink-0 rounded-md p-1.5 text-ink-muted hover:bg-raised hover:text-ink
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <TrashIcon className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="flex gap-2 border-t border-hairline pt-3">
        <input
          className="min-w-0 flex-1 rounded-lg border border-hairline bg-raised px-3 py-2 text-sm text-ink
                     placeholder:text-ink-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          value={nuevo}
          onChange={(e) => setNuevo(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && crear()}
          placeholder="Nueva etiqueta: pádel, escalada…"
        />
        <Button onClick={crear} disabled={!nuevo.trim()} className="px-3 py-1.5 text-xs">
          Crear
        </Button>
      </div>
      {error && <p className="text-xs text-err">{error}</p>}
    </div>
  )
}
