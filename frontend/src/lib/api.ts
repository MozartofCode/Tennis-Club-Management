import { useAuth } from './auth'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) {
      const field = detail[0].loc?.slice(-1)[0]
      return field ? `${field}: ${detail[0].msg}` : detail[0].msg
    }
  }
  return fallback
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = useAuth.getState().token
  const isForm = options.body instanceof FormData
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
    method: options.method ?? (options.body ? 'POST' : 'GET'),
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.body && !isForm ? { 'Content-Type': 'application/json' } : {}),
    },
    body: isForm ? (options.body as FormData) : options.body ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(0, "Can't reach CourtIQ. Check your connection and try again.")
  }
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    // Not JSON: usually a proxy error page because the API isn't running.
    throw new ApiError(res.status, res.status >= 500 ? "Can't reach the CourtIQ server. Is the API running (make dev)?" : `Unexpected response (${res.status})`)
  }
  if (!res.ok) {
    if (res.status === 401 && token) useAuth.getState().signOut()
    throw new ApiError(res.status, messageFrom(body, `Request failed (${res.status})`))
  }
  return body as T
}
