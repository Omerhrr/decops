<template>
  <section class="card mt-6 p-6" aria-labelledby="tz-title">
    <h2 id="tz-title" class="text-base font-semibold text-ink">Time zone</h2>
    <p class="mt-1 text-sm text-muted">Dates and times across DecOps are shown in this zone.</p>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <select v-model="tz" class="select-field !w-auto max-w-full" aria-label="Time zone" @change="saveTz">
        <option v-for="z in zones" :key="z" :value="z">{{ z }}</option>
      </select>
      <button type="button" class="btn-secondary px-3 py-1.5" @click="useBrowserTz">Use this device's zone</button>
      <span v-if="tzMessage" role="status" class="text-sm text-muted">{{ tzMessage }}</span>
    </div>
  </section>

  <section class="card mt-6 p-6" aria-labelledby="np-title">
    <h2 id="np-title" class="text-base font-semibold text-ink">Notifications</h2>
    <p class="mt-1 text-sm text-muted">Choose where you hear about each kind of event.</p>
    <div class="mt-4 overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead class="text-left text-xs uppercase tracking-wide text-muted">
          <tr><th class="py-2 pr-4">Event</th><th class="px-4 py-2">In app</th><th class="px-4 py-2">Email</th></tr>
        </thead>
        <tbody class="divide-y divide-line">
          <tr v-for="e in EVENTS" :key="e.key">
            <td class="py-2 pr-4 text-body">{{ e.label }}</td>
            <td class="px-4 py-2"><input type="checkbox" class="h-4 w-4" :checked="get(e.key).in_app" :aria-label="`${e.label}: in app`" @change="set(e.key, 'in_app', ($event.target as HTMLInputElement).checked)"></td>
            <td class="px-4 py-2"><input type="checkbox" class="h-4 w-4" :checked="get(e.key).email" :aria-label="`${e.label}: email`" @change="set(e.key, 'email', ($event.target as HTMLInputElement).checked)"></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="error" role="alert" class="mt-3 text-sm text-rose-600 dark:text-rose-400">{{ error }}</p>
    <div v-if="auth.hasPermission('settings.manage')" class="mt-5 border-t border-line pt-4">
      <button type="button" class="btn-secondary" :disabled="testing" @click="sendTest">{{ testing ? 'Sending…' : 'Send a test email to me' }}</button>
      <p v-if="testMessage" role="status" class="mt-2 text-sm text-muted">{{ testMessage }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
const api = useApi()
const auth = useAuth()

const EVENTS = [
  { key: 'task_assigned', label: 'Task assigned to me' },
  { key: 'supporting_pm_added', label: 'Added as supporting PM' },
  { key: 'comment_mention', label: 'Mentioned in a comment' },
  { key: 'deadline_approaching', label: 'Deadline approaching' },
  { key: 'task_overdue', label: 'Task overdue' },
  { key: 'task_blocked', label: 'Task blocked' },
  { key: 'blocker_resolved', label: 'Blocker resolved' },
  { key: 'task_submitted_for_review', label: 'Review requested' },
  { key: 'review_rejected', label: 'Review rejected' },
  { key: 'task_completed', label: 'Task completed' },
  { key: 'task_reopened', label: 'Task reopened' },
  { key: 'work_item_completed', label: 'Work item completed' },
  { key: 'milestone_completed', label: 'Milestone completed' },
  { key: 'visibility_changed', label: 'Visibility changed' },
  { key: 'access_granted', label: 'Access granted' },
  { key: 'access_revoked', label: 'Access changed' },
]

const zones = (() => {
  try { return ['UTC', ...(Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf('timeZone')] } catch { return ['UTC'] }
})()
const tz = ref(auth.user.value?.preferences?.timezone || 'UTC')
const tzMessage = ref('')
async function saveTz() {
  tzMessage.value = ''
  try {
    await api.put('/api/v1/me/preferences', { timezone: tz.value })
    setDisplayTimeZone(tz.value)
    if (auth.user.value) auth.user.value = { ...auth.user.value, preferences: { ...(auth.user.value.preferences as object), timezone: tz.value } as never }
    tzMessage.value = 'Saved.'
  } catch (e) {
    tzMessage.value = e instanceof Error ? e.message : 'Could not save.'
  }
}
function useBrowserTz() {
  tz.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  if (!zones.includes(tz.value)) zones.push(tz.value)
  saveTz()
}

const prefs = reactive<Record<string, { in_app: boolean, email: boolean }>>({})
const error = ref('')
const testing = ref(false)
const testMessage = ref('')

function get(key: string) {
  return prefs[key] ?? { in_app: true, email: true }
}

async function set(key: string, channel: 'in_app' | 'email', value: boolean) {
  const next = { ...get(key), [channel]: value }
  const before = get(key)
  prefs[key] = next
  error.value = ''
  try {
    await api.put('/api/v1/notifications/preferences', {
      event_type: key, in_app_enabled: next.in_app, email_enabled: next.email,
    })
  } catch (e) {
    prefs[key] = before
    error.value = e instanceof Error ? e.message : 'Could not save that preference.'
  }
}

async function sendTest() {
  testing.value = true
  testMessage.value = ''
  try {
    const r = await api.post<{ sent_to: string }>('/api/v1/notifications/test-email')
    testMessage.value = `Test email sent to ${r.sent_to}.`
  } catch (e) {
    testMessage.value = e instanceof Error ? e.message : 'Could not send the test email.'
  } finally {
    testing.value = false
  }
}

onMounted(async () => {
  try {
    const res = await api.get<{ preferences: { event_type: string, in_app_enabled: boolean, email_enabled: boolean }[] }>('/api/v1/notifications/preferences')
    for (const p of res.preferences) prefs[p.event_type] = { in_app: p.in_app_enabled, email: p.email_enabled }
  } catch { /* defaults apply */ }
})
</script>
