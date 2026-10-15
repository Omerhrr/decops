// In-app notification state (Phase 6): unread badge + notification center.
// Polls the API on an interval while the user is authenticated; processing is
// server-side (transactional outbox worker) - the client only reads results.

import type { NotificationItem } from '~/types/api'

export function useNotifications() {
  const unread = useState<number>('notifications.unread', () => 0)
  const items = useState<NotificationItem[]>('notifications.items', () => [])
  const loaded = useState<boolean>('notifications.loaded', () => false)
  const auth = useAuth()
  const api = useApi()
  let timer: ReturnType<typeof setInterval> | null = null

  async function fetchUnread(): Promise<void> {
    if (!auth.isAuthenticated.value) return
    try {
      const data = await api.get<{ unread: number }>('/api/v1/notifications/unread-count')
      unread.value = data.unread
    } catch {
      // Session may have expired mid-poll; the auth middleware handles redirects.
    }
  }

  async function fetchList(limit = 20): Promise<void> {
    if (!auth.isAuthenticated.value) return
    try {
      const data = await api.get<{ items: NotificationItem[], unread: number }>(
        `/api/v1/notifications?limit=${limit}`,
      )
      items.value = data.items
      unread.value = data.unread
      loaded.value = true
    } catch {
      // ignore transient poll errors
    }
  }

  async function markRead(id: string): Promise<void> {
    await api.post(`/api/v1/notifications/${id}/read`)
    const item = items.value.find(i => i.id === id)
    if (item && !item.read_at) {
      item.read_at = new Date().toISOString()
      if (unread.value > 0) unread.value -= 1
    }
  }

  async function markAllRead(): Promise<void> {
    await api.post('/api/v1/notifications/read-all')
    const now = new Date().toISOString()
    items.value = items.value.map(i => ({ ...i, read_at: i.read_at ?? now }))
    unread.value = 0
  }

  function startPolling(intervalMs = 30000): void {
    if (!import.meta.client) return // SSR: no timers on the server
    stopPolling()
    void fetchUnread()
    timer = setInterval(() => void fetchUnread(), intervalMs)
  }

  function stopPolling(): void {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  return { unread, items, loaded, fetchUnread, fetchList, markRead, markAllRead, startPolling, stopPolling }
}
