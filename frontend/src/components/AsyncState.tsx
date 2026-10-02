import type { ReactNode } from 'react'
import { Button } from './Button'
import { Card } from './Card'
import { AlertIcon, SpinnerIcon } from './icons'

interface AsyncStateProps {
  loading: boolean
  error: string | null
  isEmpty: boolean
  emptyMessage: string
  errorPrefix: string
  onRetry: () => void
  children: ReactNode
}

export function AsyncState({ loading, error, isEmpty, emptyMessage, errorPrefix, onRetry, children }: AsyncStateProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-ink-secondary">
        <SpinnerIcon className="h-4 w-4" />
        <p className="text-sm">Cargando…</p>
      </div>
    )
  }
  if (error) {
    return (
      <Card className="flex flex-col items-center gap-3 p-6 text-center">
        <AlertIcon className="h-6 w-6 text-err" />
        <p className="text-sm text-ink-secondary">
          {errorPrefix}: {error}
        </p>
        <Button variant="ghost" onClick={onRetry}>
          Reintentar
        </Button>
      </Card>
    )
  }
  if (isEmpty) {
    return <p className="py-10 text-center text-sm text-ink-secondary">{emptyMessage}</p>
  }
  return <>{children}</>
}
