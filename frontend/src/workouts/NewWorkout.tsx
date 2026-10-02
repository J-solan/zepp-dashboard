import { useState } from 'react'
import { Button } from '../components/Button'
import { SportSuggestions } from '../components/SportSuggestions'
import { useSports } from '../hooks/useSports'
import { fetchJson } from '../lib/api'
import { clearApiCache } from '../hooks/useApi'
import { sportLabel } from '../lib/workouts'

const inputClass =
  'w-full rounded-lg border border-hairline bg-raised px-3 py-2 text-sm text-ink placeholder:text-ink-muted ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent'

const OTHER = ' otro'

/** `datetime-local` da 'YYYY-MM-DDTHH:mm' en hora LOCAL sin zona; `new Date()`
 * lo interpreta en la del navegador, que es justo la que el usuario tecleó. */
const toTs = (local: string) => Math.floor(new Date(local).getTime() / 1000)

/** Un valor inicial cómodo: hoy a las 18:00, redondeado. */
function defaultStart(): string {
  const now = new Date()
  now.setHours(18, 0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`
}

/** Alta de un entreno que hiciste sin el reloj.
 *
 * Se pide inicio y DURACIÓN, no inicio y fin: nadie recuerda a qué hora exacta
 * terminó, pero "hora y media" sí. El fin se calcula.
 *
 * Sin FC, carga ni zonas: eso lo mide el reloj y aquí no hubo reloj. Dejar los
 * campos vacíos es más honesto que ofrecer teclear un número inventado que
 * luego se mezclaría con los medidos en cualquier agregado.
 */
export function NewWorkout({ onCreated }: { onCreated: () => void }) {
  const { sports } = useSports()
  const [start, setStart] = useState(defaultStart)
  const [minutes, setMinutes] = useState('60')
  const [sport, setSport] = useState('')
  const [custom, setCustom] = useState(false)
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    const startTs = toTs(start)
    const mins = Number(minutes)
    if (!Number.isFinite(startTs)) return setError('Fecha no válida')
    if (!Number.isFinite(mins) || mins <= 0) return setError('La duración tiene que ser mayor que cero')

    setSaving(true)
    setError(null)
    try {
      await fetchJson('/api/workouts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_ts: startTs,
          end_ts: startTs + Math.round(mins * 60),
          user_sport: sport.trim() || null,
          user_title: title.trim() || null,
          notes: notes.trim() || null,
        }),
      })
      clearApiCache()
      onCreated()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-label uppercase text-ink-muted">Inicio</span>
          <input
            type="datetime-local"
            className={inputClass}
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label className="flex w-28 shrink-0 flex-col gap-1">
          <span className="text-label uppercase text-ink-muted">Minutos</span>
          <input
            type="number"
            min={1}
            className={inputClass}
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
          />
        </label>
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-label uppercase text-ink-muted">Tipo</span>
        <select
          className={inputClass}
          value={custom ? OTHER : sport}
          onChange={(e) => {
            const value = e.target.value
            setCustom(value === OTHER)
            setSport(value === OTHER ? '' : value)
          }}
        >
          <option value="">Sin clasificar</option>
          {sports.map((s) => (
            <option key={s.name} value={s.name}>
              {sportLabel(s.name)}
            </option>
          ))}
          <option value={OTHER}>Otro…</option>
        </select>
        {custom && (
          <>
            <SportSuggestions id="sugerencias-nuevo" sports={sports} />
            <input
              className={inputClass}
              list="sugerencias-nuevo"
              value={sport}
              onChange={(e) => setSport(e.target.value)}
              placeholder="pádel, escalada, natación…"
              autoFocus
            />
          </>
        )}
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-label uppercase text-ink-muted">Nombre</span>
        <input
          className={inputClass}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Rocódromo con Marta"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-label uppercase text-ink-muted">Nota</span>
        <textarea
          className={`${inputClass} resize-y`}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>

      {error && <p className="text-xs text-err">{error}</p>}

      <Button onClick={submit} disabled={saving} className="self-start px-3 py-1.5 text-xs">
        {saving ? 'Guardando…' : 'Crear entreno'}
      </Button>
    </div>
  )
}
