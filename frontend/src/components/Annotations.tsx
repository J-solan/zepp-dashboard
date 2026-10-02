import { useEffect, useRef, useState } from 'react'
import { Button } from './Button'
import { CloseIcon, NoteIcon, TrashIcon } from './icons'
import { formatTooltipTs } from '../lib/chartFormat'
import type { AnnotationEditor } from '../hooks/useAnnotationEditor'

/** Rango de una nota en texto: si empieza y acaba el mismo día basta con las
 * horas ("10:30 – 12:00"); si cruza la medianoche hace falta la fecha. */
function spanLabel(from: number, to: number): string {
  const sameDay = new Date(from * 1000).toDateString() === new Date(to * 1000).toDateString()
  const end = new Date(to * 1000)
  return sameDay
    ? `${formatTooltipTs(from)} – ${end.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}`
    : `${formatTooltipTs(from)} – ${formatTooltipTs(to)}`
}

/** Botón de anotar + formulario del tramo seleccionado + lista de notas.
 *
 * El gesto es el mismo arrastre que ya hace zoom: al activar "Anotar", pintar
 * una franja sobre la gráfica abre este formulario con el tramo puesto. */
export function Annotations({ editor }: { editor: AnnotationEditor }) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // Al seleccionar un tramo el foco va al input: se puede escribir y pulsar
  // Enter sin tocar el ratón otra vez.
  useEffect(() => {
    if (editor.pending) {
      setText('')
      inputRef.current?.focus()
    }
  }, [editor.pending])

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={editor.toggle}
          aria-pressed={editor.isAnnotating}
          className={
            'flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors ' +
            'duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ' +
            (editor.isAnnotating
              ? 'border-accent bg-accent text-page'
              : 'border-hairline bg-surface text-ink-secondary hover:text-ink')
          }
        >
          <NoteIcon className="h-4 w-4" />
          {editor.isAnnotating ? 'Marca el tramo…' : 'Anotar'}
        </button>
        {editor.isAnnotating && !editor.pending && (
          <span className="text-xs text-ink-muted">Arrastra sobre la gráfica para elegir el tramo</span>
        )}
        {editor.error && <span className="text-xs text-err">{editor.error}</span>}
      </div>

      {editor.pending && (
        <form
          className="animate-card-expand flex flex-wrap items-center gap-2 rounded-lg border border-hairline
                     bg-raised p-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (text.trim()) void editor.save(text.trim())
          }}
        >
          <span className="text-xs tabular-nums text-ink-secondary">
            {spanLabel(editor.pending.from, editor.pending.to)}
          </span>
          <input
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="¿Qué pasó aquí?"
            maxLength={200}
            className="min-w-40 flex-1 rounded-md border border-hairline bg-surface px-2 py-1.5 text-sm
                       text-ink placeholder:text-ink-muted focus-visible:outline-none focus-visible:ring-2
                       focus-visible:ring-accent"
          />
          <Button type="submit" disabled={!text.trim() || editor.saving}>
            {editor.saving ? 'Guardando…' : 'Guardar'}
          </Button>
          <Button type="button" variant="ghost" onClick={editor.cancel}>
            <CloseIcon className="h-4 w-4" />
          </Button>
        </form>
      )}

      {editor.annotations.length > 0 && (
        <ul className="flex flex-col gap-1">
          {editor.annotations.map((a) => (
            <li key={a.id} className="flex items-center gap-2 rounded-md px-1 py-0.5 text-sm">
              <span className="h-3 w-0.5 shrink-0 rounded-full bg-accent" />
              <span className="shrink-0 text-xs tabular-nums text-ink-muted">
                {spanLabel(a.start_ts, a.end_ts)}
              </span>
              <span className="min-w-0 flex-1 truncate text-ink">{a.text}</span>
              <button
                type="button"
                onClick={() => void editor.remove(a.id)}
                aria-label={`Borrar anotación: ${a.text}`}
                className="shrink-0 rounded p-1 text-ink-muted transition-colors hover:text-err
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <TrashIcon className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
