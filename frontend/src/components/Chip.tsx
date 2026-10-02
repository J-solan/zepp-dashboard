interface ChipProps {
  color: string
  label: string
  value?: string
}

export function Chip({ color, label, value }: ChipProps) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-ink-secondary">
      <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
      {label}
      {value != null && <span className="text-ink">{value}</span>}
    </span>
  )
}
