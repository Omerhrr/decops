// Typed API client. All requests go through the Nuxt server proxy on this
// origin (/api/** -> FastAPI :8000), so session cookies stay first-party and
// HttpOnly. Centralized error handling per spec frontend requirements.

import type { ApiErrorBody } from '~/types/api'

export class ApiError extends Error {
  code: string
  status: number
  details?: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody['error']) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
  }
}

export function useApi() {
  async function request<T>(
    path: string,
    options: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<T> {
    // During SSR the request originates from the Nitro server, which has no
    // cookie jar of its own: forward the incoming request's cookies so
    // session-dependent fetches (auth middleware, protected pages) resolve
    // against the visitor's real session. Client-side requests use the jar.
    const ssfCookieHeader = import.meta.server ? useRequestHeaders(['cookie']) : {}
    const response = await $fetch.raw(path, {
      method: options.method ?? 'GET',
      body: options.body,
      headers: { ...ssfCookieHeader, ...options.headers },
      credentials: 'include',
      ignoreResponseError: true,
    })

    if (response.status >= 400) {
      const body = (response._data ?? {}) as ApiErrorBody
      throw new ApiError(response.status, body.error ?? {
        code: 'unknown_error',
        message: 'Unexpected response from the server.',
      })
    }
    return response._data as T
  }

  return {
    get: <T>(path: string) => request<T>(path),
    post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
    patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
    delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  }
}
