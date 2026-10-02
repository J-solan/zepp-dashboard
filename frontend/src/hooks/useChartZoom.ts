import { useCallback, useEffect, useMemo, useState } from 'react'

/** Lo único que se necesita del estado que recharts pasa a los handlers del
 * chart: el valor de dominio bajo el cursor/dedo. Se declara aquí en vez de
 * importar `MouseHandlerDataParam` para no atarse a un tipo interno. */
interface ActivePoint {
  activeLabel?: string | number
}

interface Drag {
  from: number
  to: number
}

export interface ChartZoom {
  /** Dominio visible del eje X: el zoom activo o el rango completo. */
  domain: [number, number]
  isZoomed: boolean
  reset: () => void
  /** Selección en curso mientras se arrastra, para pintar la banda. */
  selection: Drag | null
  handlers: {
    onMouseDown: (next: ActivePoint) => void
    onMouseMove: (next: ActivePoint) => void
    onMouseUp: () => void
    onMouseLeave: () => void
    onTouchStart: (next: ActivePoint) => void
    onTouchMove: (next: ActivePoint) => void
    onTouchEnd: () => void
  }
}

/** Fracción del tramo visible por debajo de la cual un arrastre se considera
 * un clic (o un temblor de dedo) y no cuenta como selección. */
const MIN_DRAG_FRACTION = 0.02

export interface ChartZoomOptions {
  /** `select` desvía el arrastre a `onSelect` en vez de hacer zoom: es el modo
   * "anotar", que reutiliza exactamente el mismo gesto. */
  mode?: 'zoom' | 'select'
  onSelect?: (from: number, to: number) => void
}

/** Zoom por arrastre sobre el eje temporal, como el pellizco de rango de Zepp:
 * seleccionas una franja y el chart se reencuadra en ella.
 *
 * Es puramente cliente sobre los datos ya descargados — no dispara fetch, así
 * que el reencuadre es instantáneo. Con los buckets del backend (5 min en la
 * vista de semana) ampliar a un día deja ~288 puntos, resolución de sobra. */
export function useChartZoom(full: [number, number], options: ChartZoomOptions = {}): ChartZoom {
  const { mode = 'zoom', onSelect } = options
  const [zoom, setZoom] = useState<[number, number] | null>(null)
  const [drag, setDrag] = useState<Drag | null>(null)

  const [fullFrom, fullTo] = full

  // Cambiar de día/semana redefine el eje: un zoom heredado apuntaría a
  // instantes que ya no están en pantalla.
  useEffect(() => {
    setZoom(null)
    setDrag(null)
  }, [fullFrom, fullTo])

  // Referencia estable: es dependencia de los `useMemo` que calculan ticks y
  // separadores, y un array nuevo por render los invalidaría todos.
  const domain = useMemo<[number, number]>(() => zoom ?? [fullFrom, fullTo], [zoom, fullFrom, fullTo])

  const start = useCallback((next: ActivePoint) => {
    if (typeof next?.activeLabel === 'number') setDrag({ from: next.activeLabel, to: next.activeLabel })
  }, [])

  const extend = useCallback((next: ActivePoint) => {
    if (typeof next?.activeLabel !== 'number') return
    const to = next.activeLabel
    setDrag((d) => (d ? { ...d, to } : null))
  }, [])

  const commit = useCallback(() => {
    if (!drag) return
    setDrag(null)
    const from = Math.min(drag.from, drag.to)
    const to = Math.max(drag.from, drag.to)
    const [visibleFrom, visibleTo] = zoom ?? [fullFrom, fullTo]
    if (to - from < (visibleTo - visibleFrom) * MIN_DRAG_FRACTION) return
    if (mode === 'select') onSelect?.(from, to)
    else setZoom([from, to])
  }, [drag, zoom, fullFrom, fullTo, mode, onSelect])

  const reset = useCallback(() => setZoom(null), [])

  return {
    domain,
    isZoomed: zoom != null,
    reset,
    selection: drag && drag.from !== drag.to ? drag : null,
    handlers: {
      onMouseDown: start,
      onMouseMove: extend,
      onMouseUp: commit,
      onMouseLeave: commit,
      onTouchStart: start,
      onTouchMove: extend,
      onTouchEnd: commit,
    },
  }
}
