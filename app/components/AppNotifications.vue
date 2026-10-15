<template>
  <div ref="rootEl" class="relative">
    <button
      type="button"
      class="relative rounded-lg p-2 text-muted transition-colors hover:bg-hover hover:text-ink"
      aria-label="Notifications"
      :aria-expanded="open"
      data-test="notification-bell"
      @click="toggle"
    >
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
      </svg>
      <span
        v-if="unread > 0"
        class="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white"
        data-test="notification-badge"
      >
        {{ unread > 9 ? '9+' : unread }}
      </span>
    </button>

    <transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="scale-95 opacity-0"
      enter-to-class="scale-100 opacity-100"
      leave-active-class="transition duration-75 ease-in"
      leave-from-class="scale-100 opacity-100"
      leave-to-class="scale-95 opacity-0"
    >
      <div
        v-if="open"
        class="absolute right-0 z-50 mt-2 w-[21rem] origin-top-right overflow-hidden rounded-xl border border-line bg-surface shadow-xl sm:w-96"
        data-test="notification-panel"
      >
        <div class="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 class="text-sm font-semibold text-ink">Notifications</h2>
          <button
            v-if="unread > 0"
            type="button"
            class="text-xs font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300"
            @click="onMarkAllRead"
          >
            Mark all read
          </button>
        </div>

        <p v-if="loaded && items.length === 0" class="px-4 py-8 text-center text-sm text-faint">
          You're all caught up - no notifications yet.
        </p>

        <ul v-else class="max-h-96 divide-y divide-line overflow-y-auto">
          <li v-for="item in items" :key="item.id">
            <button
              type="button"
              class="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-hover"
              :class="{ ' dark:bg-brand-500/5': !item.read_at }"
              @click="onItemClick(item)"
            >
              <span
                class="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                :class="item.read_at ? 'bg-transparent' : 'bg-brand-500'"
                aria-hidden="true"
              />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium" :class="item.read_at ? 'text-muted' : 'text-ink'">
                  {{ item.payload?.title ?? eventLabel(item.event_type) }}
                </span>
                <span class="mt-0.5 block text-xs text-muted">{{ item.payload?.summary ?? eventLabel(item.event_type) }}</span>
                <span class="mt-1 block text-[11px] text-faint">{{ relativeTime(item.created_at) }}</span>
              </span>
            </button>
          </li>
        </ul>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import type { NotificationItem } from '~/types/api'

const EVENT_LABELS: Record<string, string> = {
  task_assigned: 'Task assigned',
  supporting_pm_added: 'Supporting PM added',
  deadline_approaching: 'Deadline approaching',
  task_overdue: 'Task overdue',
  work_item_completed: 'Work item completed',
  task_blocked: 'Task blocked',
  blocker_resolved: 'Blocker resolved',
  task_submitted_for_review: 'Review requested',
  review_rejected: 'Review rejected',
  task_completed: 'Task completed',
  task_reopened: 'Task reopened',
  visibility_changed: 'Visibility changed',
  access_granted: 'Access granted',
  access_revoked: 'Access revoked',
  milestone_completed: 'Milestone completed',
}

const rootEl = ref<HTMLElement | null>(null)
const open = ref(false)
const router = useRouter()
const auth = useAuth()
const { unread, items, loaded, fetchList, markRead, markAllRead, startPolling, stopPolling } = useNotifications()

function toggle(): void {
  open.value = !open.value
  if (open.value) void fetchList()
}

function eventLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType.replaceAll('_', ' ')
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

async function onItemClick(item: NotificationItem): Promise<void> {
  open.value = false
  if (!item.read_at) await markRead(item.id)
  if (item.resource_type === 'task' && item.resource_id) {
    await router.push(`/tasks/${item.resource_id}`)
  }
}

async function onMarkAllRead(): Promise<void> {
  await markAllRead()
}

function onDocumentClick(event: MouseEvent): void {
  if (open.value && rootEl.value && !rootEl.value.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  stopPolling()
})

// Poll only while signed in; stop immediately on logout.
watch(
  () => auth.isAuthenticated.value,
  (authenticated) => {
    if (authenticated) startPolling()
    else {
      stopPolling()
      unread.value = 0
      items.value = []
      open.value = false
    }
  },
  { immediate: true },
)
</script>
