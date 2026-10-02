import { Card } from './Card'

interface StatCardProps {
  label: string
  value: string
  sub?: string
}

export function StatCard({ label, value, sub }: StatCardProps) {
  return (
    <Card className="p-4">
      <p className="text-label uppercase text-ink-muted">{label}</p>
      <p className="mt-1.5 text-3xl font-semibold text-ink">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-ink-secondary">{sub}</p>}
    </Card>
  )
}
