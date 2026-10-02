import { useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import { AsyncState } from '../components/AsyncState'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import type { SeriesSpec } from '../components/TimeSeriesChart'
import { Chip } from '../components/Chip'
import type { TabProps } from '../App'
import { BIO } from '../lib/palette'
import type { BiochargeSample } from '../lib/types'

// Solo "Total" lleva relleno degradado: es la serie protagonista. Mental y
// físico van de línea limpia porque se cruzan constantemente y tres áreas
// superpuestas embarran la lectura.
const SERIES: SeriesSpec[] = [
  { dataKey: 'total', name: 'Total', color: BIO.total },
  { dataKey: 'mental', name: 'Mental', color: BIO.mental, fillOpacity: 0 },
  { dataKey: 'physical', name: 'Físico', color: BIO.physical, fillOpacity: 0 },
]

export function HybridChargeDetail({ range }: TabProps) {
  const { data, loading, error, refetch } = useApi<BiochargeSample[]>(
    `/api/biocharge?from=${range.from}&to=${range.to}`,
  )

  // Serie ya agregada por el servidor; total llega null en el
  // centinela (255 filtrado en ingesta) -> hueco. Solo se descarta `status`.
  const chartData = useMemo(
    () => (data ?? []).map((d) => ({ ts: d.ts, total: d.total, mental: d.mental, physical: d.physical })),
    [data],
  )

  return (
    <div className="flex flex-col gap-4">
      <AsyncState
        loading={loading && !data}
        error={error}
        isEmpty={!!data && data.length === 0}
        emptyMessage="Sin datos de Hybrid Charge en este rango."
        errorPrefix="No se pudo cargar Hybrid Charge"
        onRetry={refetch}
      >
        {data && data.length > 0 && (
          <>
            <div className="flex flex-wrap gap-3">
              <Chip color={BIO.total} label="Total" />
              <Chip color={BIO.mental} label="Mental" />
              <Chip color={BIO.physical} label="Físico" />
            </div>
            <TimeSeriesChart
              data={chartData}
              series={SERIES}
              range={range}
              yDomain={[0, 100]}
              height="lg"
              loading={loading}
            />
          </>
        )}
      </AsyncState>
    </div>
  )
}
