import { Button } from '../components/Button'
import { AlertIcon, CheckIcon, SpinnerIcon } from '../components/icons'
import { STEPS, type Step } from './client'

export interface BootState {
  step: Step
  ready: boolean
  error: string | null
}

/** Pantalla de carga del modo demo: qué es esto y por qué paso del arranque va. */
export function BootScreen({ step, error }: BootState) {
  const current = Object.keys(STEPS).indexOf(step)
  return (
    <main className="mx-auto flex min-h-svh max-w-sm flex-col justify-center gap-6 px-4 py-10">
      <div className="flex flex-col gap-3">
        <h1 className="flex items-baseline gap-2">
          <span className="font-serif text-2xl leading-none tracking-tight">Helio</span>
          <span className="text-label uppercase text-accent">demo</span>
        </h1>
        <p className="text-sm text-ink-secondary">
          Todo corre en tu navegador con datos inventados; no hay servidor ni datos reales. Al recargar vuelve a
          empezar.
        </p>
      </div>

      <ol className="flex flex-col gap-2 border-t border-hairline pt-4 text-sm" aria-live="polite">
        {Object.entries(STEPS).map(([key, label], i) => {
          const done = i < current
          const active = i === current
          return (
            <li
              key={key}
              aria-current={active ? 'step' : undefined}
              className={`flex items-center gap-2 ${active ? 'font-medium text-ink' : done ? 'text-ink-secondary' : 'text-ink-muted'}`}
            >
              <span className="flex size-4 shrink-0 items-center justify-center">
                {done ? (
                  <CheckIcon className="size-4 text-ok" />
                ) : active && error ? (
                  <AlertIcon className="size-4 text-err" />
                ) : active ? (
                  <SpinnerIcon className="size-4 text-accent" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-ink opacity-40" />
                )}
              </span>
              {label}
              {active && !error && '…'}
            </li>
          )
        })}
      </ol>

      {error && (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-card border border-hairline bg-surface p-4">
          <p className="text-sm">No se pudo arrancar la demo.</p>
          <p className="font-mono text-xs text-ink-secondary">{error}</p>
          <Button onClick={() => location.reload()}>Reintentar</Button>
        </div>
      )}
    </main>
  )
}
