import type { ReactNode } from 'react'
import { Card } from './Card'
import { SpinnerIcon, ZoomOutIcon } from './icons'

interface ChartFrameProps {
  title?: string
  height?: 'sm' | 'md' | 'lg'
  /** Recarga en curso con datos ya en pantalla: se atenúa la gráfica vieja en
   * vez de sustituirla por un spinner a pantalla completa, que hacía saltar la
   * altura de la tarjeta y parecía que la app se colgaba al cambiar de rango. */
  loading?: boolean
  onResetZoom?: () => void
  children: ReactNode
}

const HEIGHTS: Record<NonNullable<ChartFrameProps['height']>, string> = {
  sm: 'h-48',
  md: 'h-64',
  lg: 'h-72',
}

export function ChartFrame({ title, height = 'md', loading = false, onResetZoom, children }: ChartFrameProps) {
  return (
    <Card className="relative p-4">
      {title && <p className="mb-3 text-label uppercase text-ink-muted">{title}</p>}

      <div
        className={`w-full transition-opacity duration-200 ${HEIGHTS[height]} ${loading ? 'opacity-40' : 'opacity-100'}`}
      >
        {children}
      </div>

      {loading && (
        <span className="pointer-events-none absolute right-4 top-4 text-ink-secondary">
          <SpinnerIcon className="h-4 w-4" />
        </span>
      )}

      {onResetZoom && !loading && (
        <button
          type="button"
          onClick={onResetZoom}
          className="animate-fade-in absolute right-4 top-4 flex items-center gap-1.5 rounded-md border
                     border-hairline bg-raised/90 px-2 py-1 text-xs font-medium text-ink-secondary backdrop-blur
                     transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2
                     focus-visible:ring-accent"
        >
          <ZoomOutIcon className="h-3.5 w-3.5" />
          Ver todo
        </button>
      )}
    </Card>
  )
}
