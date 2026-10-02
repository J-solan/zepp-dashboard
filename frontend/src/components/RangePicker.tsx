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
            onClick={() => onChange(presetRange(p.id, value.to), p.id)}
          >
            {p.label}
          </button>
        ))}
        <button className={tabClass(activePreset === 'custom')} onClick={() => onChange(value, 'custom')}>
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
          <input
            type="date"
            value={value.from}
            max={value.to}
            onChange={(e) => onChange({ ...value, from: e.target.value }, 'custom')}
            className="rounded-md border border-hairline bg-raised px-2 py-2"
          />
          <span className="text-ink-muted">–</span>
          <input
            type="date"
            value={value.to}
            min={value.from}
            max={todayISO()}
            onChange={(e) => onChange({ ...value, to: e.target.value }, 'custom')}
            className="rounded-md border border-hairline bg-raised px-2 py-2"
          />
        </span>
      )}
    </div>
  )
}
