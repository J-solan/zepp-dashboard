import type { TooltipPayloadEntry } from 'recharts'
import { formatTooltipDay, formatTooltipTs } from '../lib/chartFormat'

interface ChartTooltipProps {
  active?: boolean
  payload?: ReadonlyArray<TooltipPayloadEntry<number, string>>
  label?: string | number
  labelKind: 'ts' | 'day'
  unit?: string
}

export function ChartTooltip({ active, payload, label, labelKind, unit }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null

  const rows = payload.filter((entry) => entry.value != null)
  if (rows.length === 0) return null

  const labelText =
    labelKind === 'ts' ? formatTooltipTs(Number(label)) : formatTooltipDay(String(label))

  return (
    <div className="rounded-lg border border-hairline bg-raised px-3 py-2 shadow-raised">
      <p className="text-xs text-ink-muted">{labelText}</p>
      <div className="mt-1 flex flex-col gap-1">
        {rows.map((entry, i) => (
          <div key={entry.dataKey != null ? String(entry.dataKey) : i} className="flex items-center gap-2 text-sm">
            <span
              className="h-0.5 w-3 shrink-0 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="font-semibold text-ink tabular-nums">
              {Math.round(Number(entry.value))}
              {unit ? ` ${unit}` : ''}
            </span>
            {rows.length > 1 && <span className="text-ink-secondary">{entry.name}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
