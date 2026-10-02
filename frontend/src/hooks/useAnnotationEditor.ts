import { useCallback, useEffect, useState } from 'react'
import { useAnnotations } from './useAnnotations'
import type { DateRange } from '../lib/dateRange'
import type { Annotation } from '../lib/types'

export interface PendingSpan {
  from: number
  to: number
}

export interface AnnotationEditor {
  annotations: Annotation[]
  error: string | null
  /** Modo "anotar" activo: el arrastre sobre la gráfica selecciona en vez de
   * hacer zoom. */
  isAnnotating: boolean
  toggle: () => void
  /** Tramo ya seleccionado, a la espera de que se escriba el texto. */
  pending: PendingSpan | null
  select: (from: number, to: number) => void
  cancel: () => void
  save: (text: string) => Promise<void>
  remove: (id: number) => Promise<void>
  saving: boolean
}

/** Estado del alta de anotaciones sobre una gráfica.
 *
 * Vive en un hook y no en cada detalle porque FC y estrés necesitan el mismo
 * cableado exacto, y las notas son compartidas: lo que se crea desde FC tiene
 * que aparecer igual en estrés. */
export function useAnnotationEditor(range: DateRange): AnnotationEditor {
  const { annotations, error, create, remove } = useAnnotations(range)
  const [isAnnotating, setIsAnnotating] = useState(false)
  const [pending, setPending] = useState<PendingSpan | null>(null)
  const [saving, setSaving] = useState(false)

  // Cambiar de día con una selección a medias dejaría un tramo que ya no se ve.
  useEffect(() => {
    setPending(null)
    setIsAnnotating(false)
  }, [range.from, range.to])

  const toggle = useCallback(() => {
    setIsAnnotating((on) => !on)
    setPending(null)
  }, [])

  const save = useCallback(
    async (text: string) => {
      if (!pending) return
      setSaving(true)
      try {
        await create(pending.from, pending.to, text)
        setPending(null)
        setIsAnnotating(false)
      } finally {
        setSaving(false)
      }
    },
    [pending, create],
  )

  return {
    annotations,
    error,
    isAnnotating,
    toggle,
    pending,
    select: useCallback((from: number, to: number) => setPending({ from, to }), []),
    cancel: useCallback(() => setPending(null), []),
    save,
    remove,
    saving,
  }
}
