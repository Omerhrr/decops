<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <!-- Header -->
    <section class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <nav class="text-xs text-slate-400" aria-label="Breadcrumb">
          <NuxtLink to="/" class="hover:text-slate-600">Dashboard</NuxtLink>
          <span class="mx-1">/</span>
          <span class="text-slate-600">Tasks</span>
        </nav>
        <h1 class="mt-1 text-xl font-semibold text-slate-900">Task register</h1>
        <p class="mt-1 text-sm text-slate-500">
          Every task you are authorized to see (MOD-003). Access is evaluated per task by the policy engine.
        </p>
      </div>
      <button
        v-if="canCreate"
        type="button"
        class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700"
        @click="showCreate = true"
      >
        + Create task
      </button>
    </section>

    <!-- Filters -->
    <section class="mt-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center">
      <input
        v-model="query"
        type="search"
        placeholder="Search by number, title, or description…"
        class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500 sm:max-w-sm"
        @input="debouncedLoad"
      />
      <select
        v-model="statusFilter"
        class="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
        @change="loadTasks"
      >
        <option value="">All statuses</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ statusLabel(s) }}</option>
      </select>
      <select
        v-model="priorityFilter"
        class="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
        @change="loadTasks"
      >
        <option value="">All priorities</option>
        <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
      </select>
      <span class="text-sm text-slate-400 sm:ml-auto">{{ total }} tasks</span>
    </section>

    <!-- Register table -->
    <section class="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Number</th>
            <th class="px-4 py-3">Title</th>
            <th class="px-4 py-3">Accountable PM</th>
            <th class="px-4 py-3">Departments</th>
            <th class="px-4 py-3">Priority</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Progress</th>
            <th class="px-4 py-3">Due date</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="loading">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Loading…</td>
          </tr>
          <tr v-else-if="!tasks.length">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">
              No authorized tasks match the filters.
            </td>
          </tr>
          <tr v-for="t in tasks" :key="t.id" class="cursor-pointer hover:bg-slate-50/60" @click="openTask(t.id)">
            <td class="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-600">{{ t.task_number }}</td>
            <td class="px-4 py-3">
              <p class="font-medium text-slate-900">{{ t.title }}</p>
              <p class="text-xs text-slate-400">{{ visibilityLabel(t.visibility_mode) }} visibility</p>
            </td>
            <td class="px-4 py-3 text-slate-600">{{ t.accountable_pm?.full_name ?? '-' }}</td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap gap-1">
                <AppBadge v-for="name in t.department_names" :key="name" tone="gray">{{ name }}</AppBadge>
                <span v-if="!t.department_names.length" class="text-xs text-slate-400"> - </span>
              </div>
            </td>
            <td class="px-4 py-3">
              <AppBadge :tone="priorityTone(t.priority)">{{ t.priority }}</AppBadge>
            </td>
            <td class="px-4 py-3">
              <AppBadge :tone="statusTone(t.status)">{{ statusLabel(t.status) }}</AppBadge>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <div class="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                  <div class="h-full rounded-full bg-brand-500" :style="{ width: `${t.percent_complete}%` }" />
                </div>
                <span class="text-xs text-slate-500">{{ t.percent_complete }}%</span>
              </div>
            </td>
            <td class="whitespace-nowrap px-4 py-3 text-xs" :class="isOverdue(t) ? 'font-medium text-rose-600' : 'text-slate-500'">
              {{ formatDate(t.due_date) }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-end gap-2 text-sm">
      <button
        type="button"
        class="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
        :disabled="page <= 1"
        @click="page--; loadTasks()"
      >
        Previous
      </button>
      <span class="text-slate-500">Page {{ page }} of {{ totalPages }}</span>
      <button
        type="button"
        class="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
        :disabled="page >= totalPages"
        @click="page++; loadTasks()"
      >
        Next
      </button>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" @click.self="showCreate = false">
      <div class="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold text-slate-900">Create task</h2>
        <p class="mt-1 text-sm text-slate-500">
          New tasks start as drafts. The access policy is established at creation.
        </p>

        <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label class="sm:col-span-2 block">
            <span class="text-xs font-medium text-slate-600">Title *</span>
            <input
              v-model="form.title"
              type="text"
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
              placeholder="What needs to be done?"
            />
          </label>
          <label class="sm:col-span-2 block">
            <span class="text-xs font-medium text-slate-600">Description</span>
            <textarea
              v-model="form.description"
              rows="3"
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
              placeholder="Background, instructions, acceptance expectations…"
            />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-slate-600">Priority</span>
            <select v-model="form.priority" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
          <label class="block">
            <span class="text-xs font-medium text-slate-600">Accountable PM *</span>
            <select v-model="form.accountable_pm_id" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="">Select a person…</option>
              <option :value="meId">{{ meName }} (me)</option>
              <option v-for="u in candidatePMs" :key="u.id" :value="u.id">{{ u.full_name }}</option>
            </select>
          </label>
          <label class="block">
            <span class="text-xs font-medium text-slate-600">Start date</span>
            <input v-model="form.start_date" type="date" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-slate-600">Due date</span>
            <input v-model="form.due_date" type="date" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-slate-600">Visibility</span>
            <select v-model="form.visibility_mode" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="participants">Participants - the project team</option>
              <option value="private">Private - invited people only</option>
              <option value="department_scoped">Department scoped</option>
              <option value="custom">Custom - explicit grants only</option>
            </select>
          </label>
          <label v-if="form.visibility_mode === 'department_scoped'" class="block">
            <span class="text-xs font-medium text-slate-600">Department *</span>
            <select v-model="form.department_id" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="">Select a department…</option>
              <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </label>
        </div>

        <p v-if="createError" class="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ createError }}</p>

        <div class="mt-6 flex justify-end gap-3">
          <button type="button" class="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100" @click="showCreate = false">
            Cancel
          </button>
          <button
            type="button"
            class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            :disabled="creating"
            @click="createTask"
          >
            {{ creating ? 'Creating…' : 'Create task' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Department, Task, TaskPage, TaskPriority, TaskStatus } from '~/types/api'

const api = useApi()
const auth = useAuth()

const STATUSES: TaskStatus[] = ['draft', 'open', 'in_progress', 'blocked', 'under_review', 'completed', 'cancelled', 'archived']
const PRIORITIES: TaskPriority[] = ['low', 'medium', 'high', 'critical']

const tasks = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 25
const loading = ref(true)
const query = ref('')
const statusFilter = ref('')
const priorityFilter = ref('')

const canCreate = computed(() => auth.hasPermission('tasks.create'))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// create-modal state
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const departments = ref<Department[]>([])
const candidatePMs = ref<{ id: string, full_name: string }[]>([])
const meId = computed(() => auth.user.value?.id ?? '')
const meName = computed(() => auth.displayName.value)
const form = reactive({
  title: '',
  description: '',
  priority: 'medium' as TaskPriority,
  accountable_pm_id: '',
  start_date: '',
  due_date: '',
  visibility_mode: 'participants',
  department_id: '',
})

const statusLabel = (s: string) => s.replaceAll('_', ' ')
const visibilityLabel = (v: string) => v.replaceAll('_', ' ')
const priorityTone = (p: string) =>
  p === 'critical' ? 'rose' : p === 'high' ? 'amber' : p === 'medium' ? 'gray' : 'green'

function statusTone(s: string): 'green' | 'amber' | 'gray' | 'rose' {
  switch (s) {
    case 'completed': return 'green'
    case 'open':
    case 'in_progress': return 'amber'
    case 'blocked': return 'rose'
    case 'cancelled': return 'rose'
    default: return 'gray'
  }
}

function isOverdue(t: Task): boolean {
  if (!t.due_date || ['completed', 'cancelled', 'archived'].includes(t.status)) return false
  return new Date(t.due_date).getTime() < Date.now()
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function openTask(id: string) {
  navigateTo(`/tasks/${id}`)
}

async function loadTasks() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize))
    if (query.value.trim()) params.set('q', query.value.trim())
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (priorityFilter.value) params.set('priority', priorityFilter.value)
    const data = await api.get<TaskPage>(`/api/v1/tasks?${params.toString()}`)
    tasks.value = data.items
    total.value = data.total
  } catch {
    tasks.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

let debounceTimer: ReturnType<typeof setTimeout> | undefined
function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    loadTasks()
  }, 300)
}

async function loadFormOptions() {
  // Directory + departments power the create modal; failures are non-fatal.
  try {
    const users = await api.get<{ items: { id: string, full_name: string, account_status: string }[] }>('/api/v1/users?page_size=100')
    candidatePMs.value = users.items
      .filter(u => u.account_status === 'active' && u.id !== meId.value)
      .map(u => ({ id: u.id, full_name: u.full_name }))
  } catch { /* directory needs users.manage - hide the options */ }
  try {
    departments.value = await api.get<Department[]>('/api/v1/departments')
  } catch { /* departments need departments.manage - hide the options */ }
}

async function createTask() {
  createError.value = ''
  if (!form.title.trim()) { createError.value = 'Please provide a title.'; return }
  if (!form.accountable_pm_id) { createError.value = 'Please select the accountable PM.'; return }
  creating.value = true
  try {
    const payload: Record<string, unknown> = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      priority: form.priority,
      accountable_pm_id: form.accountable_pm_id,
      start_date: form.start_date || null,
      due_date: form.due_date || null,
      visibility_mode: form.visibility_mode,
    }
    if (form.visibility_mode === 'department_scoped') {
      if (!form.department_id) {
        createError.value = 'Department-scoped tasks need at least one department.'
        creating.value = false
        return
      }
      payload.department_ids = [form.department_id]
    }
    const created = await api.post<{ id: string }>('/api/v1/tasks', payload)
    showCreate.value = false
    navigateTo(`/tasks/${created.id}`)
  } catch (err) {
    createError.value = err instanceof Error ? err.message : 'Could not create the task.'
  } finally {
    creating.value = false
  }
}

watch(showCreate, (open) => {
  if (open) {
    createError.value = ''
    if (!departments.value.length || !candidatePMs.value.length) loadFormOptions()
  }
})

onMounted(loadTasks)
useHead({ title: 'Task register - DecOps' })
</script>
