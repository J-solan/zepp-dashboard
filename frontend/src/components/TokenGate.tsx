import { useEffect, useRef, useState, type FormEvent } from 'react'
import { authRequired, getToken, setToken } from '../lib/api'
import { Button } from './Button'

const inputClass =
  'w-full rounded-lg border border-hairline bg-raised px-3 py-2 text-sm text-ink placeholder:text-ink-muted ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent'

/** Pantalla "Token de acceso". Solo aparece si el backend tiene `api_token` y
 * ha respondido 401. Guarda el token en este navegador y recarga, así cada
 * vista reintenta ya con él. */
export function TokenGate() {
  const [open, setOpen] = useState(false)
  const [rejected, setRejected] = useState(false)
  const [value, setValue] = useState('')
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const onRequired = () => {
      setRejected(getToken() !== null) // había uno guardado y aun así 401: no vale
      setOpen(true)
    }
    authRequired.addEventListener('required', onRequired)
    return () => authRequired.removeEventListener('required', onRequired)
  }, [])

  useEffect(() => {
    if (open) ref.current?.showModal()
  }, [open])

  if (!open) return null

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const token = value.trim()
    if (!token) return
    setToken(token)
    location.reload()
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="token-gate-title"
      // Sin token la app no sirve: Escape no cierra. Chrome no deja cancelar el
      // primer Escape si aún no ha habido interacción, así que se reabre.
      onCancel={(e) => e.preventDefault()}
      onClose={() => ref.current?.showModal()}
      className="fixed inset-0 m-auto w-full max-w-sm bg-transparent p-6 backdrop:bg-page/95"
    >
      <form onSubmit={submit} className="w-full space-y-4 rounded-card border border-hairline bg-surface p-6">
        <h2 id="token-gate-title" className="text-lg font-medium text-ink">
          Token de acceso
        </h2>
        {rejected && (
          <p role="alert" className="text-sm text-ink">
            El token guardado no es válido.
          </p>
        )}
        <p className="text-sm text-ink-secondary">
          Este servidor pide el <code>api_token</code> de su config. Se guarda en este navegador.
        </p>
        <label className="block space-y-1.5 text-sm text-ink-secondary">
          <span>Token</span>
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            className={inputClass}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <Button type="submit" className="w-full" disabled={!value.trim()}>
          Guardar
        </Button>
      </form>
    </dialog>
  )
}
