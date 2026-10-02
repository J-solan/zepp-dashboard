const TOKEN_KEY = 'zepp-dashboard:api-token'

/** Emite 'required' cuando la API responde 401: el backend tiene `api_token`
 * y no se lo hemos mandado (o no es el bueno). Lo escucha `TokenGate`. */
export const authRequired = new EventTarget()

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null // modo privado o almacenamiento bloqueado: se va sin token
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Sin almacenamiento no hay dónde guardarlo: el siguiente 401 lo volverá a pedir.
  }
}

/** `fetch` con el token del backend, si hay uno guardado. Es el único punto de
 * red de la app: todo `/api/*` pasa por aquí. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) authRequired.dispatchEvent(new Event('required'))
  return res
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `Error ${res.status} en ${path}`)
  }
  // 204 (p.ej. DELETE de una anotación) no trae cuerpo: parsearlo reventaría.
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
