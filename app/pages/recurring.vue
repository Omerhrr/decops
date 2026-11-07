<template>
  <div class="mx-auto max-w-4xl px-4 py-8 sm:px-6">
    <nav class="text-xs text-faint" aria-label="Breadcrumb">
      <NuxtLink to="/" class="hover:text-body">Dashboard</NuxtLink><span class="mx-1">/</span><span class="text-body">Recurring tasks</span>
    </nav>
    <h1 class="mt-1 text-xl font-semibold text-ink">Recurring tasks</h1>
    <p class="mt-1 text-sm text-muted">A normal task is created for you on each schedule. Missed periods are skipped, not backfilled.</p>

    <form class="card mt-6 grid grid-cols-1 gap-4 p-5 sm:grid-cols-2" @submit.prevent="create">
      <label class="block sm:col-span-2"><span class="text-xs font-medium text-body">Title *</span>
        <input v-model="form.title" class="input-field mt-1" minlength="3" maxlength="200" required placeholder="e.g. Weekly stock count"></label>
      <label class="block"><span class="text-xs font-medium text-body">Repeats</span>
        <select v-model="form.frequency" class="input-field mt-1"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
      <label class="block"><span class="text-xs font-medium text-body">Every N periods</span>
        <input v-model.number="form.interval" type="number" min="1" max="12" class="input-field mt-1"></label>
      <label class="block"><span class="text-xs font-medium text-body">First run</span>
        <input v-model="form.first_run_on" type="date" class="input-field mt-1"></label>
      <label class="block"><span class="text-xs font-medium text-body">Due after (days)</span>
        <input v-model.number="form.due_after_days" type="number" min="0" max="365" class="input-field mt-1"></label>
      <label class="block"><span class="text-xs font-medium text-body">Priority</span>
        <select v-model="form.priority" class="input-field mt-1"><option v-for="p in ['low','medium','high','critical']" :key="p" :value="p">{{ capitalize(p) }}</option></select></label>
      <label class="block"><span class="text-xs font-medium text-body">Accountable PM *</span>
        <select v-model="form.accountable_pm_id" class="input-field mt-1" required>
          <option :value="auth.user.value?.id">{{ auth.displayName.value }} (me)</option>
          <option v-for="u in people" :key="u.id" :value="u.id">{{ u.full_name }}</option>
        </select></label>
      <div class="sm:col-span-2 flex items-center justify-between gap-3">
        <p v-if="error" role="alert" class="text-sm text-rose-600 dark:text-rose-400">{{ error }}</p><span v-else />
        <button type="submit" class="btn-primary" :disabled="saving">{{ saving ? 'Saving…' : 'Add recurring task' }}</button>
      </div>
    </form>

    <ul class="mt-6 space-y-3" aria-label="Recurring tasks">
      <li v-if="!items.length" class="card empty-state"><p>No recurring tasks yet.</p></li>
      <li v-for="r in items" :key="r.id" class="card flex flex-wrap items-center justify-between gap-3 p-4">
        <div class="min-w-0">
          <p class="font-medium text-ink">{{ r.title }}</p>
          <p class="text-xs text-muted">Every {{ r.interval > 1 ? r.interval + ' ' : '' }}{{ r.frequency }} · next {{ formatDate(r.next_run_on) }} · due after {{ r.due_after_days }}d · {{ r.active ? 'active' : 'paused' }}</p>
          <p v-if="r.last_error" class="text-xs text-rose-600 dark:text-rose-400">Last run failed: {{ r.last_error }}</p>
        </div>
        <div class="flex gap-2">
          <button type="button" class="btn-secondary px-3 py-1.5" @click="toggle(r.id)">{{ r.active ? 'Pause' : 'Resume' }}</button>
          <button type="button" class="btn-secondary px-3 py-1.5" @click="remove(r.id)">Delete</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
interface Rec { id: string, title: string, frequency: string, interval: number, due_after_days: number, next_run_on: string, active: boolean, last_error: string | null }

const api = useApi()
const auth = useAuth()
const items = ref<Rec[]>([])
const people = ref<{ id: string, full_name: string }[]>([])
const saving = ref(false)
const error = ref('')
const form = reactive({
  title: '', frequency: 'weekly', interval: 1, first_run_on: '', due_after_days: 7,
  priority: 'medium', accountable_pm_id: auth.user.value?.id ?? '',
})

async function load() {
  try { items.value = await api.get<Rec[]>('/api/v1/integrations/recurring') } catch { items.value = [] }
}
async function create() {
  error.value = ''
  saving.value = true
  try {
    await api.post('/api/v1/integrations/recurring', { ...form, first_run_on: form.first_run_on || null })
    form.title = ''
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not save.'
  } finally { saving.value = false }
}
async function toggle(id: string) { try { await api.post(`/api/v1/integrations/recurring/${id}/toggle`) } finally { await load() } }
async function remove(id: string) { try { await api.delete(`/api/v1/integrations/recurring/${id}`) } finally { await load() } }

onMounted(async () => {
  await load()
  try {
    const res = await api.get<{ items: { id: string, full_name: string, account_status: string }[] }>('/api/v1/users?page_size=100')
    people.value = res.items.filter(u => u.account_status === 'active' && u.id !== auth.user.value?.id)
  } catch { /* directory needs users.manage; only "me" is offered */ }
})
useHead({ title: 'Recurring tasks - DecOps' })
</script>
