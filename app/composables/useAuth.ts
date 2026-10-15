// Session state: who is signed in. The session lives in an HttpOnly cookie,
// so the client never touches the token itself (server-managed sessions).

import type { Me } from '~/types/api'

export function useAuth() {
  const user = useState<Me | null>('auth.user', () => null)
  const loaded = useState('auth.loaded', () => false)
  const api = useApi()

  const isAuthenticated = computed(() => !!user.value)
  const displayName = computed(() => user.value?.full_name ?? '')
  const roleNames = computed(() => (user.value?.roles ?? []).map(r => r.name))

  function hasPermission(...codes: string[]): boolean {
    const held = user.value?.permissions ?? []
    return codes.some(code => held.includes(code))
  }

  async function fetchMe(): Promise<Me | null> {
    try {
      user.value = await api.get<Me>('/api/v1/auth/me')
    } catch {
      user.value = null
    } finally {
      loaded.value = true
    }
    return user.value
  }

  async function login(email: string, password: string): Promise<void> {
    user.value = await api.post<Me>('/api/v1/auth/login', { email, password })
    loaded.value = true
  }

  async function logout(): Promise<void> {
    try {
      await api.post('/api/v1/auth/logout')
    } finally {
      user.value = null
      await navigateTo('/login')
    }
  }

  return { user, loaded, isAuthenticated, displayName, roleNames, hasPermission, fetchMe, login, logout }
}
