import { useMemo } from 'react'
import { ReferenceArea } from 'recharts'
import { useApi } from '../hooks/useApi'
import { useAnnotationEditor } from '../hooks/useAnnotationEditor'
import { AsyncState } from '../components/AsyncState'
import { Annotations } from '../components/Annotations'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { Chip } from '../components/Chip'
import type { TabProps } from '../App'
import { Card } from '../components/Card'
import { StatCard } from '../components/StatCard'
import { WeekBars } from '../components/WeekBars'
import { useWeekSeries } from './useWeekReference'
import { METRIC, ZONE } from '../lib/palette'
import type { StressSeries } from '../lib/types'

// Zonas de referencia visual (aproximadas a las de la app Zepp; no vienen
// como umbrales del backend, es solo una guía de lectura del área).
const ZONES = [
  { from: 0, to: 39, color: ZONE.relaxed, label: 'Relajado' },
  { from: 40, to: 59, color: ZONE.normal, label: 'Normal' },
  { from: 60, to: 79, color: ZONE.medium, label: 'Medio' },
  { from: 80, to: 100, color: ZONE.high, label: 'Alto' },
]

// El strap mide el estrés cada ~6 min, no cada minuto. Con el bucket de 60 s
// que elige el servidor por defecto, entre cada dos muestras cae un marcador de
// hueco y NO queda ni un solo segmento de línea que dibujar: el día salía como
// una nube de puntos sueltos. A 15 min cada bucket agrupa un par de medidas
// reales y la serie vuelve a ser continua.
const DAY_BUCKET_S = 900

export function StressDetail({ range }: TabProps) {
  // Un día se lee mejor como barras (cada medida es un evento suelto, como en
  // Zepp); en semana y mes ya hay muestras de sobra para un área continua.
  const isDay = range.from === range.to

  const { data, loading, error, refetch } = useApi<StressSeries>(
    `/api/stress?from=${range.from}&to=${range.to}${isDay ? `&bucket=${DAY_BUCKET_S}` : ''}`,
  )
  const notes = useAnnotationEditor(range)

  // El servidor entrega {series (agregada + huecos null), stats (exactos)}.
  const chartData = useMemo(() => data?.series ?? [], [data])

  const stats = data?.stats ?? null

  // Contexto de la semana: el rango elegido dice cómo ha ido HOY, no si eso
  // es normal para ti.
  const week = useWeekSeries((row) => row.stress_avg)

  return (
    <div className="flex flex-col gap-4">
      <AsyncState
        loading={loading && !data}
        error={error}
        isEmpty={!!data && data.series.length === 0}
        emptyMessage="Sin datos de estrés en este rango."
        errorPrefix="No se pudo cargar el estrés"
        onRetry={refetch}
      >
        {data && data.series.length > 0 && stats && stats.min != null && stats.avg != null && stats.max != null && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <StatCard label="Mín" value={`${Math.round(stats.min)}`} />
              <StatCard label="Media del rango" value={`${Math.round(stats.avg)}`} />
              <StatCard label="Máx" value={`${Math.round(stats.max)}`} />
            </div>
            <Card className="flex flex-col gap-2 p-4">
              <p className="text-label uppercase text-ink-muted">Media diaria · 7 días</p>
              <WeekBars data={week} color={METRIC.stress} format={(v) => `${Math.round(v)}`} />
            </Card>
            <div className="flex flex-wrap gap-3">
              {ZONES.map((z) => (
                <Chip key={z.label} color={z.color} label={`${z.label} (${z.from}–${z.to})`} />
              ))}
            </div>
            <Annotations editor={notes} />
            <TimeSeriesChart
              data={chartData}
              series={[{ dataKey: 'value', color: METRIC.stress, kind: isDay ? 'bar' : 'area' }]}
              range={range}
              yDomain={[0, 100]}
              loading={loading}
              annotations={notes.annotations}
              annotate={{ active: notes.isAnnotating, onSelect: notes.select }}
              background={ZONES.map((z) => (
                <ReferenceArea key={z.label} y1={z.from} y2={z.to} fill={z.color} fillOpacity={0.06} />
              ))}
            />
          </>
        )}
      </AsyncState>
    </div>
  )
}
