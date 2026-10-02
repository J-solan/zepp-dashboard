import { useId, useMemo, type ReactNode } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartFrame } from './ChartFrame'
import { ChartTooltip } from './ChartTooltip'
import { useChartZoom } from '../hooks/useChartZoom'
import { dayBoundaryTs, dayStartTs, rangeBoundsTs } from '../lib/date'
import { timeAxis } from '../lib/chartFormat'
import { CHART } from '../lib/palette'
import type { DateRange } from '../lib/dateRange'
import type { Annotation } from '../lib/types'

export interface SeriesSpec {
  dataKey: string
  color: string
  name?: string
  /** `bar` para series muestreadas de tanto en tanto (el estrés llega cada
   * ~6 min): una línea entre muestras tan separadas no se puede dibujar sin
   * inventar el tramo intermedio, así que cada medida se pinta como su propia
   * barra. `area` para series continuas al minuto (FC, BioCharge). */
  kind?: 'area' | 'bar'
  /** Opacidad del gradiente en la parte alta. 0 = solo línea (para series
   * secundarias que se superponen y embarrarían el relleno). */
  fillOpacity?: number
}

interface TimeSeriesChartProps {
  /** Filas con `ts` (unix s) y una clave por serie. El resto de campos no se
   * tipa aquí porque los `dataKey` de recharts son strings sueltos. */
  data: ReadonlyArray<{ ts: number }>
  series: SeriesSpec[]
  /** Rango de días pedido al backend: fija el encuadre del eje X. */
  range: DateRange
  /** Encuadre [inicio, fin] en unix s que sustituye al del rango completo.
   * Lo usa el detalle de un entreno: sobre el día entero, una hora de FC sería
   * un pico de 4 px. `range` sigue haciendo falta para anclar los ticks a las
   * medianoches locales. */
  bounds?: [number, number]
  yDomain?: [number | string, number | string]
  unit?: string
  height?: 'sm' | 'md' | 'lg'
  loading?: boolean
  /** Elementos de recharts pintados bajo las series (p.ej. bandas de zona). */
  background?: ReactNode
  /** Notas manuales del rango: se pintan como banda vertical sobre la serie. */
  annotations?: Annotation[]
  /** Con `active`, el arrastre selecciona un tramo para anotar en vez de
   * hacer zoom (mismo gesto, distinto destino). */
  annotate?: { active: boolean; onSelect: (from: number, to: number) => void }
}

/** Gráfica temporal común a todas las métricas intradía.
 *
 * Tres decisiones que la separan de un LineChart pelado:
 *  - **Eje X numérico** (`type="number"` + dominio del rango). Con el eje de
 *    categorías por defecto los puntos se repartían a intervalos iguales, así
 *    que un hueco de 3 h sin pulsera ocupaba lo mismo que un minuto y un día
 *    con datos solo de mañana llenaba todo el ancho. Ahora el tiempo es
 *    proporcional y un día siempre se encuadra de 00:00 a 24:00.
 *  - **Relleno degradado** bajo la línea, que da volumen sin tapar la rejilla.
 *  - **Zoom por arrastre** sobre una franja, con botón para volver. */
export function TimeSeriesChart({
  data,
  series,
  range,
  bounds: boundsProp,
  yDomain,
  unit,
  height = 'md',
  loading = false,
  background,
  annotations,
  annotate,
}: TimeSeriesChartProps) {
  const gradPrefix = useId().replace(/:/g, '')

  const bounds = useMemo(
    () => boundsProp ?? rangeBoundsTs(range.from, range.to),
    [boundsProp, range.from, range.to],
  )
  // Ancla de la rejilla horaria: SIEMPRE la medianoche del primer día, aunque
  // el encuadre empiece a las 18:37 por un `bounds` de entreno — si no, los
  // ticks caerían en 18:37, 18:52… en vez de en las horas en punto.
  const dayStarts = useMemo(
    () => [dayStartTs(range.from), ...dayBoundaryTs(range.from, range.to)],
    [range.from, range.to],
  )

  const zoom = useChartZoom(bounds, {
    mode: annotate?.active ? 'select' : 'zoom',
    onSelect: annotate?.onSelect,
  })
  const axis = useMemo(() => timeAxis(zoom.domain[0], zoom.domain[1], dayStarts), [zoom.domain, dayStarts])

  // Separadores solo en multi-día y solo los que caen dentro del zoom actual.
  const separators = useMemo(
    () => dayStarts.slice(1).filter((ts) => ts > zoom.domain[0] && ts < zoom.domain[1]),
    [dayStarts, zoom.domain],
  )

  return (
    <ChartFrame height={height} loading={loading} onResetZoom={zoom.isZoomed ? zoom.reset : undefined}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data as { ts: number }[]}
          margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          // pan-y: el arrastre horizontal selecciona, el vertical sigue
          // haciendo scroll de la página.
          style={{ touchAction: 'pan-y', userSelect: 'none', cursor: 'crosshair' }}
          {...zoom.handlers}
        >
          <defs>
            {series.map((s) => (
              <linearGradient key={s.dataKey} id={`${gradPrefix}-${s.dataKey}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={s.fillOpacity ?? 0.35} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>

          <CartesianGrid vertical={false} stroke={CHART.grid} />
          {background}
          {separators.map((ts) => (
            <ReferenceLine key={ts} x={ts} stroke={CHART.grid} strokeDasharray="3 4" />
          ))}
          {annotations?.map((a) => (
            <ReferenceArea
              key={a.id}
              x1={a.start_ts}
              x2={a.end_ts}
              fill={CHART.annotation}
              fillOpacity={0.14}
              stroke={CHART.annotation}
              strokeOpacity={0.5}
            />
          ))}

          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={zoom.domain}
            allowDataOverflow
            ticks={axis.ticks}
            tickFormatter={axis.format}
            tickLine={false}
            axisLine={false}
            minTickGap={24}
            tickMargin={8}
            tick={{ fontSize: 11, fill: CHART.axis }}
          />
          <YAxis
            domain={yDomain ?? ['dataMin - 5', 'dataMax + 5']}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: CHART.axis }}
            width={32}
          />
          <Tooltip content={<ChartTooltip labelKind="ts" unit={unit} />} cursor={{ stroke: CHART.grid }} />

          {series.map((s) =>
            s.kind === 'bar' ? (
              <Bar
                key={s.dataKey}
                dataKey={s.dataKey}
                name={s.name}
                fill={s.color}
                fillOpacity={0.85}
                radius={[2, 2, 0, 0]}
                isAnimationActive={false}
              />
            ) : (
              <Area
                key={s.dataKey}
                type="monotone"
                dataKey={s.dataKey}
                name={s.name}
                stroke={s.color}
                strokeWidth={2}
                strokeLinecap="round"
                fill={s.fillOpacity === 0 ? 'none' : `url(#${gradPrefix}-${s.dataKey})`}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: CHART.surface }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ),
          )}

          {zoom.selection && (
            <ReferenceArea
              x1={Math.min(zoom.selection.from, zoom.selection.to)}
              x2={Math.max(zoom.selection.from, zoom.selection.to)}
              fill={annotate?.active ? CHART.annotation : CHART.axis}
              fillOpacity={annotate?.active ? 0.25 : 0.18}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}
