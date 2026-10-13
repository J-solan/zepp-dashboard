import { useState } from 'react'
import { PRESETS, presetRange, rangeLabel, shiftRange } from '../lib/dateRange'
import type { DateRange, Preset } from '../lib/dateRange'
import { todayISO } from '../lib/date'
import { ChevronLeftIcon, ChevronRightIcon } from './icons'

interface RangePickerProps {
  value: DateRange
  activePreset: Preset
  onChange: (range: DateRange, preset: Preset) => void
}

// El activo va en tinta plena y no en un escalón de gris: sobre papel dos
// tonos casi iguales no marcan cuál está seleccionado.
const tabClass = (active: boolean) =>
  'shrink-0 rounded-sm px-3 py-1 text-sm font-medium transition-colors duration-150 ' +
  (active ? 'bg-ink text-page' : 'text-ink-secondary hover:text-ink')

const arrowClass =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-secondary transition-colors duration-150 ' +
  'hover:bg-raised hover:text-ink disabled:pointer-events-none disabled:opacity-30 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent'

// Suelo de "desde". Al teclear un año el campo pasa por 0002, 0020, 0202…:
// sin `min` son fechas válidas, y un rango de siglos congelaba la pestaña.
const MIN_DAY = '2000-01-01'

/** Campo de fecha que solo aplica fechas válidas.
 *
 * Vacía (borrada o a medio teclear) o fuera de su `min`/`max`, no se aplica y
 * se queda el rango anterior: aplicarla mandaba `from=` (422) y la etiqueta
 * pintaba "Invalid Date". Lo que no vale se queda en un borrador local y no se
 * le devuelve al campo el valor aplicado a cada tecla, porque eso impedía
 * teclear un año (pasa por 0002, 0020…). Al salir del campo vuelve la fecha
 * aplicada. */
function DateField({ label, value, min, max, onCommit }: {
  label: string
  value: string
  min?: string
  max?: string
  onCommit: (day: string) => void
}) {
  // Atado a la fecha aplicada: si cambia por fuera (las flechas), el borrador
  // viejo deja de valer solo.
  const [draft, setDraft] = useState<{ base: string; text: string } | null>(null)
  return (
    <input
      type="date"
      aria-label={label}
      value={draft?.base === value ? draft.text : value}
      min={min}
      max={max}
      onChange={(e) => {
        const { value: text, validity } = e.target
        if (text && validity.valid) {
          setDraft(null)
          onCommit(text)
        } else {
          setDraft({ base: value, text })
        }
      }}
      onBlur={() => setDraft(null)}
      className="rounded-md border border-hairline bg-raised px-2 py-2"
    />
  )
}

/** Selector de rango estilo Zepp: pestañas de granularidad (Día/Semana/Mes) y
 * un par de flechas que recorren el histórico ventana a ventana. Al cambiar de
 * granularidad se re-ancla en el último día visible, no en hoy, para no perder
 * el sitio cuando estás mirando una fecha pasada. */
export function RangePicker({ value, activePreset, onChange }: RangePickerProps) {
  const prev = shiftRange(value, activePreset, -1)
  const next = shiftRange(value, activePreset, 1)

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex gap-0.5 rounded-md border border-hairline bg-surface p-0.5">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className={tabClass(activePreset === p.id)}
            aria-pressed={activePreset === p.id}
            onClick={() => onChange(presetRange(p.id, value.to), p.id)}
          >
            {p.label}
          </button>
        ))}
        <button
          className={tabClass(activePreset === 'custom')}
          aria-pressed={activePreset === 'custom'}
          onClick={() => onChange(value, 'custom')}
        >
          Fechas
        </button>
      </div>

      <div className="flex items-center gap-0.5">
        <button
          className={arrowClass}
          onClick={() => prev && onChange(prev, activePreset)}
          disabled={!prev}
          aria-label="Rango anterior"
        >
          <ChevronLeftIcon className="h-4 w-4" />
        </button>
        <span className="min-w-28 text-center font-mono text-sm tabular-nums text-ink">{rangeLabel(value)}</span>
        <button
          className={arrowClass}
          onClick={() => next && onChange(next, activePreset)}
          disabled={!next}
          aria-label="Rango siguiente"
        >
          <ChevronRightIcon className="h-4 w-4" />
        </button>
      </div>

      {activePreset === 'custom' && (
        <span className="flex w-full items-center gap-1.5 text-sm text-ink">
          <DateField
            label="Desde"
            value={value.from}
            min={MIN_DAY}
            max={value.to}
            onCommit={(from) => onChange({ ...value, from }, 'custom')}
          />
          <span className="text-ink-muted">–</span>
          <DateField
            label="Hasta"
            value={value.to}
            min={value.from}
            max={todayISO()}
            onCommit={(to) => onChange({ ...value, to }, 'custom')}
          />
        </span>
      )}
    </div>
  )
}
