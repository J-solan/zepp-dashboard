import { useId, useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi } from '../hooks/useApi'
import { AsyncState } from '../components/AsyncState'
import { ChartFrame } from '../components/ChartFrame'
import { ChartTooltip } from '../components/ChartTooltip'
import { Chip } from '../components/Chip'
import { Card } from '../components/Card'
import type { TabProps } from '../App'
import { StatCard } from '../components/StatCard'
import { Hypnogram } from '../components/Hypnogram'
import { STAGE_COLORS, STAGE_LABELS, mainSessionPerDay } from '../lib/sleep'
import { formatDuration } from '../lib/format'
import { formatAxisDay, formatTooltipDay } from '../lib/chartFormat'
import { CHART, METRIC } from '../lib/palette'
import type { SleepSession } from '../lib/types'

const MINUTE_FIELDS: { key: 'deep_min' | 'light_min' | 'rem_min' | 'awake_min'; stage: number }[] = [
  { key: 'light_min', stage: 4 },
  { key: 'deep_min', stage: 5 },
  { key: 'awake_min', stage: 7 },
  { key: 'rem_min', stage: 8 },
]

export function SleepDetail({ range }: TabProps) {
  const gradId = `sleep-trend-${useId().replace(/:/g, '')}`

  const { data, loading, error, refetch } = useApi<SleepSession[]>(`/api/sleep?from=${range.from}&to=${range.to}`)

  const mainSessions = useMemo(() => mainSessionPerDay(data ?? []), [data])
  const latest = mainSessions.length > 0 ? mainSessions[mainSessions.length - 1] : null

  // Un solo día no tiene tendencia que pintar: el score es un dato, no una
  // gráfica de un punto. Con varios días manda la tendencia y el hipnograma
  // pasa a ser el detalle de la noche que se elija en ella.
  const singleDay = range.from === range.to
  const [pickedDay, setPickedDay] = useState<string | null>(null)
  const shown = singleDay
    ? latest
    : (mainSessions.find((s) => s.day === pickedDay) ?? latest)

  return (
    <div className="flex flex-col gap-4">
      <AsyncState
        loading={loading && !data}
        error={error}
        isEmpty={!!data && data.length === 0}
        emptyMessage="Sin sesiones de sueño en este rango."
        errorPrefix="No se pudo cargar el sueño"
        onRetry={refetch}
      >
        {shown && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatCard label="Score" value={shown.score != null ? `${shown.score}` : 'Sin datos'} />
              <StatCard
                label="Duración"
                value={formatDuration((shown.end_ts - shown.start_ts) / 60)}
                sub={shown.day}
              />
              <StatCard
                label="FC reposo"
                value={shown.resting_hr != null ? `${shown.resting_hr}` : 'Sin datos'}
              />
            </div>

            {!singleDay && (
              <ChartFrame title="Tendencia del score" height="sm" loading={loading}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={mainSessions}
                    margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                    onClick={(state) => {
                      const day = (state as { activeLabel?: string } | null)?.activeLabel
                      if (day) setPickedDay(day)
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <defs>
                      <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={METRIC.sleep} stopOpacity={0.35} />
                        <stop offset="100%" stopColor={METRIC.sleep} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke={CHART.grid} />
                    <XAxis
                      dataKey="day"
                      tickFormatter={formatAxisDay}
                      tickLine={false}
                      axisLine={false}
                      minTickGap={24}
                      tickMargin={8}
                      tick={{ fontSize: 11, fill: CHART.axis }}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: CHART.axis }}
                      width={32}
                    />
                    <Tooltip content={<ChartTooltip labelKind="day" />} cursor={{ stroke: CHART.grid }} />
                    {/* La noche abierta abajo se marca en la tendencia: si no,
                        al pinchar un pico no se sabe cuál se está mirando. */}
                    {shown && <ReferenceLine x={shown.day} stroke={METRIC.sleep} strokeDasharray="3 3" />}
                    <Area
                      type="monotone"
                      dataKey="score"
                      stroke={METRIC.sleep}
                      strokeWidth={2}
                      strokeLinecap="round"
                      fill={`url(#${gradId})`}
                      dot={{ r: 3, fill: METRIC.sleep, strokeWidth: 0 }}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: CHART.surface }}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartFrame>
            )}

            <Card className="flex flex-col gap-3 p-4">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-label uppercase text-ink-muted">Hipnograma</p>
                <p className="text-xs text-ink-secondary">
                  {formatTooltipDay(shown.day)}
                  {!singleDay && <span className="text-ink-muted"> · toca la tendencia para cambiar</span>}
                </p>
              </div>
              <Hypnogram session={shown} />
              <div className="flex flex-wrap gap-3">
                {MINUTE_FIELDS.map((f) => (
                  <Chip
                    key={f.key}
                    color={STAGE_COLORS[f.stage]}
                    label={STAGE_LABELS[f.stage]}
                    value={shown[f.key] != null ? `${shown[f.key]} min` : '–'}
                  />
                ))}
              </div>
            </Card>
          </>
        )}
      </AsyncState>
    </div>
  )
}
