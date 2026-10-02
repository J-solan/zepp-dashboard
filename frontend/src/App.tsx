import { useState, type ComponentType } from 'react'
import { Nav, TabBar } from './components/Nav'
import { TokenGate } from './components/TokenGate'
import { CalendarIcon, DumbbellIcon, GridIcon } from './components/icons'
import { Panel } from './dashboard/Panel'
import { Temporada } from './tabs/Temporada'
import { Workouts } from './tabs/Workouts'
import { defaultRange } from './lib/dateRange'
import type { DateRange, Preset } from './lib/dateRange'

const ICON_CLASS = 'h-full w-full'

/** Lo que recibe cada pestaña. El rango es de la app, no de la pestaña: al
 * cambiar de Panel a Entrenos se sigue mirando la misma ventana de tiempo. */
export interface TabProps {
  range: DateRange
}

// Añadir una pestaña = añadir una entrada aquí con su componente. Ver docs/04-web.md.
const TABS = [
  { id: 'panel', label: 'Panel', icon: <GridIcon className={ICON_CLASS} />, Component: Panel },
  { id: 'temporada', label: 'Temporada', icon: <CalendarIcon className={ICON_CLASS} />, Component: Temporada },
  { id: 'entrenos', label: 'Entrenos', icon: <DumbbellIcon className={ICON_CLASS} />, Component: Workouts },
] as const satisfies readonly { id: string; label: string; icon: React.ReactNode; Component: ComponentType<TabProps> }[]

type TabId = (typeof TABS)[number]['id']

function App() {
  const [active, setActive] = useState<TabId>('panel')
  const initial = defaultRange('month')
  const [range, setRange] = useState<DateRange>(initial.range)
  const [preset, setPreset] = useState<Preset>(initial.preset)

  const ActiveComponent = TABS.find((t) => t.id === active)!.Component

  return (
    // Instalada como PWA la ventana llega a los bordes físicos (viewport-fit=
    // cover), así que el notch y la barra de gestos se comerían la nav y el
    // último elemento de la lista. `box-sizing: border-box` de Tailwind hace
    // que este padding entre DENTRO del min-h-svh, sin desbordar.
    <div
      className="mx-auto flex min-h-svh max-w-[1440px] flex-col bg-page
                 [padding-bottom:env(safe-area-inset-bottom)] [padding-top:env(safe-area-inset-top)]"
    >
      <Nav
        tabs={TABS}
        active={active}
        onSelect={setActive}
        range={range}
        activePreset={preset}
        onRangeChange={(r, p) => {
          setRange(r)
          setPreset(p)
        }}
      />
      <main className="flex-1">
        <ActiveComponent range={range} />
      </main>
      <TabBar tabs={TABS} active={active} onSelect={setActive} />
      <TokenGate />
    </div>
  )
}

export default App
