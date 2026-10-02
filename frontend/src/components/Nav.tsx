import type { ReactNode } from 'react'
import { RangePicker } from './RangePicker'
import type { DateRange, Preset } from '../lib/dateRange'

interface Tab<TId extends string> {
  id: TId
  label: string
  icon: ReactNode
}

interface NavProps<TId extends string> {
  tabs: readonly Tab<TId>[]
  active: TId
  onSelect: (id: TId) => void
  range: DateRange
  activePreset: Preset
  onRangeChange: (range: DateRange, preset: Preset) => void
}

/** Cabecera de la app: nombre, pestañas y EL selector de rango.
 *
 * El rango vive aquí y no dentro de cada tarjeta. Antes cada detalle montaba
 * el suyo, así que ver "el último mes" en cuatro métricas eran cuatro clics
 * repetidos y cada una podía estar mirando una ventana distinta.
 *
 * En móvil las pestañas no caben en esta fila y se van a `TabBar`, abajo,
 * que es donde llega el pulgar.
 */
export function Nav<TId extends string>({
  tabs,
  active,
  onSelect,
  range,
  activePreset,
  onRangeChange,
}: NavProps<TId>) {
  return (
    <header className="sticky top-0 z-10 border-b border-ink bg-page/90 backdrop-blur">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 px-4 py-3">
        <div className="flex items-baseline gap-7">
          <span className="font-serif text-2xl leading-none tracking-tight">Helio</span>
          <div className="hidden items-baseline gap-5 sm:flex">
            {tabs.map((tab) => {
              const isActive = tab.id === active
              return (
                <button
                  key={tab.id}
                  onClick={() => onSelect(tab.id)}
                  aria-current={isActive ? 'page' : undefined}
                  className={
                    'border-b-2 pb-1 text-sm transition-colors focus-visible:outline-none ' +
                    'focus-visible:ring-2 focus-visible:ring-accent ' +
                    (isActive
                      ? 'border-accent font-medium text-ink'
                      : 'border-transparent text-ink-secondary hover:text-ink')
                  }
                >
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        <RangePicker value={range} activePreset={activePreset} onChange={onRangeChange} />
      </div>
    </header>
  )
}

/** Las mismas pestañas, abajo y con icono, para móvil. */
export function TabBar<TId extends string>({
  tabs,
  active,
  onSelect,
}: Pick<NavProps<TId>, 'tabs' | 'active' | 'onSelect'>) {
  return (
    <nav className="sticky bottom-0 z-10 flex border-t border-hairline bg-page/95 backdrop-blur sm:hidden">
      {tabs.map((tab) => {
        const isActive = tab.id === active
        return (
          <button
            key={tab.id}
            onClick={() => onSelect(tab.id)}
            aria-current={isActive ? 'page' : undefined}
            className={
              'flex flex-1 flex-col items-center gap-1 py-2 text-[10px] transition-colors ' +
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ' +
              (isActive ? 'font-medium text-accent' : 'text-ink-muted')
            }
          >
            <span className="h-5 w-5">{tab.icon}</span>
            {tab.label}
          </button>
        )
      })}
    </nav>
  )
}
