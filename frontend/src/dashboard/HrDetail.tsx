import { useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import { useAnnotationEditor } from '../hooks/useAnnotationEditor'
import { AsyncState } from '../components/AsyncState'
import { Annotations } from '../components/Annotations'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import type { TabProps } from '../App'
import { Card } from '../components/Card'
import { StatCard } from '../components/StatCard'
import { WeekBars } from '../components/WeekBars'
import { useWeekSeries } from './useWeekReference'
import { METRIC } from '../lib/palette'
import type { HrSeries } from '../lib/types'

export function HrDetail({ range }: TabProps) {
  const { data, loading, error, refetch } = useApi<HrSeries>(`/api/hr?from=${range.from}&to=${range.to}`)
  const notes = useAnnotationEditor(range)

  // El servidor entrega {series (ya agregada + huecos null), stats (exactos
  // sobre el crudo)}: aquí solo se renombra bpm -> value para Recharts.
  const chartData = useMemo(() => (data?.series ?? []).map((d) => ({ ts: d.ts, value: d.bpm })), [data])

  const stats = data?.stats ?? null

  // Contexto de la semana: el rango elegido dice cómo ha ido HOY, no si eso
  // es normal para ti.
  const week = useWeekSeries((row) => row.resting_hr)

  return (
    <div className="flex flex-col gap-4">
      <AsyncState
        loading={loading && !data}
        error={error}
        isEmpty={!!data && data.series.length === 0}
        emptyMessage="Sin datos de FC en este rango."
        errorPrefix="No se pudo cargar la FC"
        onRetry={refetch}
      >
        {data && data.series.length > 0 && stats && stats.min != null && stats.avg != null && stats.max != null && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <StatCard label="Mín" value={`${Math.round(stats.min)}`} />
              <StatCard label="Media" value={`${Math.round(stats.avg)}`} />
              <StatCard label="Máx" value={`${Math.round(stats.max)}`} />
            </div>
            <Card className="flex flex-col gap-2 p-4">
              <p className="text-label uppercase text-ink-muted">FC en reposo · 7 días</p>
              <WeekBars data={week} color={METRIC.hr} format={(v) => `${Math.round(v)} bpm`} />
            </Card>
            <Annotations editor={notes} />
            <TimeSeriesChart
              data={chartData}
              series={[{ dataKey: 'value', color: METRIC.hr }]}
              range={range}
              unit="bpm"
              loading={loading}
              annotations={notes.annotations}
              annotate={{ active: notes.isAnnotating, onSelect: notes.select }}
            />
          </>
        )}
      </AsyncState>
    </div>
  )
}
