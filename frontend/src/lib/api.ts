/** Thin fetch wrapper around the Invoice Keeper API.
 *
 * Responsibilities:
 *  - always send cookies (server-side sessions),
 *  - attach the CSRF header for state-changing requests (double-submit cookie),
 *  - turn non-2xx responses into a typed error carrying the server message,
 *  - surface 401 so the app can drop to the login screen.
 */

const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export class UnauthorizedError extends ApiError {
  constructor(detail = 'Сессия истекла') {
    super(401, detail)
    this.name = 'UnauthorizedError'
  }
}

function readCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

export function getCsrfToken(): string {
  return readCookie('invoice_session_csrf')
}

interface RequestOptions {
  method?: string
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  formData?: FormData
  signal?: AbortSignal
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {}

  if (method !== 'GET' && method !== 'HEAD') {
    headers['X-CSRF-Token'] = getCsrfToken()
  }

  let body: BodyInit | undefined
  if (options.formData) {
    body = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body,
      credentials: 'same-origin',
      signal: options.signal,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(0, 'Сервер недоступен. Проверьте соединение.')
  }

  if (response.status === 401) {
    throw new UnauthorizedError()
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const detail = extractDetail(payload) ?? `Ошибка ${response.status}`
    throw new ApiError(response.status, detail)
  }

  return payload as T
}

function extractDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const record = payload as Record<string, unknown>
  const detail = record.detail
  if (typeof detail === 'string') return detail
  // FastAPI validation errors arrive as a list of {loc, msg, type}
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return null
      })
      .filter(Boolean)
    return messages.length ? messages.join('; ') : null
  }
  return null
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query']) =>
    apiRequest<T>(path, { method: 'GET', query }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, formData: FormData) =>
    apiRequest<T>(path, { method: 'POST', formData }),
}
