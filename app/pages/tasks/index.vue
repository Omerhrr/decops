<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <nav class="text-xs text-faint" aria-label="Breadcrumb">
          <NuxtLink to="/" class="hover:text-body">Dashboard</NuxtLink>
          <span class="mx-1">/</span>
          <span class="text-body">Tasks</span>
        </nav>
        <h1 class="mt-1 text-xl font-semibold text-ink">Task register</h1>
        <p class="mt-1 text-sm text-muted">
          Every task you are authorized to see (MOD-003). Access is evaluated per task by the policy engine.
        </p>
      </div>
      <button
        v-if="canCreate"
        type="button"
        class="btn-primary"
        @click="showCreate = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
        New task
      </button>
    </section>

    <section class="card mt-6 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <input
        v-model="query"
        type="search"
        placeholder="Search by number, title, or description"
        class="input-field sm:max-w-sm"
        aria-label="Search tasks"
        @input="debouncedLoad"
      />
      <select v-model="statusFilter" class="select-field" aria-label="Filter by status" @change="loadTasks">
        <option value="">All statuses</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ statusLabel(s) }}</option>
      </select>
      <select v-model="priorityFilter" class="select-field" aria-label="Filter by priority" @change="loadTasks">
        <option value="">All priorities</option>
        <option v-for="p in PRIORITIES" :key="p" :value="p">{{ capitalize(p) }}</option>
      </select>
      <span class="text-sm text-muted sm:ml-auto">{{ total }} task{{ total === 1 ? '' : 's' }}</span>
    </section>

    <section class="mt-4 overflow-x-auto rounded-2xl border border-line bg-surface">
      <table class="min-w-full divide-y divide-line text-sm">
        <thead class="bg-elevated text-left text-xs uppercase tracking-wide text-muted">
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
        <tbody class="divide-y divide-line">
          <tr v-if="loading">
            <td colspan="8" class="px-4 py-2">
              <div class="space-y-2 py-2" aria-busy="true" aria-label="Loading tasks">
                <div v-for="i in 5" :key="i" class="h-10 animate-pulse rounded-lg bg-hover" />
              </div>
            </td>
          </tr>
          <tr v-else-if="!tasks.length">
            <td colspan="8">
              <div class="empty-state">
                <svg class="h-8 w-8 text-faint" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 13.875l2.25-2.25M12 13.875l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
                </svg>
                <p class="mt-2">No authorized tasks match the filters.</p>
                <button v-if="hasActiveFilters" type="button" class="btn-secondary mt-3" @click="clearFilters">
                  Clear filters
                </button>
              </div>
            </td>
          </tr>
          <tr v-for="t in tasks" :key="t.id" class="cursor-pointer transition-colors hover:bg-hover" @click="openTask(t.id)">
            <td class="table-cell whitespace-nowrap font-mono text-xs text-body">{{ t.task_number }}</td>
            <td class="table-cell">
              <NuxtLink :to="`/tasks/${t.id}`" class="font-medium text-ink hover:text-brand-700 dark:hover:text-brand-300" @click.stop>
                {{ t.title }}
              </NuxtLink>
              <p class="text-xs text-muted">{{ visibilityLabel(t.visibility_mode) }} visibility</p>
            </td>
            <td class="px-4 py-3 text-body">{{ t.accountable_pm?.full_name ?? '-' }}</td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap gap-1">
                <AppBadge v-for="name in t.department_names" :key="name" tone="gray">{{ name }}</AppBadge>
                <span v-if="!t.department_names.length" class="text-xs text-faint"> - </span>
              </div>
            </td>
            <td class="px-4 py-3">
              <AppBadge :tone="priorityTone(t.priority)">{{ capitalize(t.priority) }}</AppBadge>
            </td>
            <td class="px-4 py-3">
              <AppBadge :tone="statusTone(t.status)">{{ statusLabel(t.status) }}</AppBadge>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <div class="h-1.5 w-16 overflow-hidden rounded-full bg-hover">
                  <div class="h-full rounded-full bg-brand-500" :style="{ width: `${t.percent_complete}%` }" />
                </div>
                <span class="text-xs text-muted">{{ t.percent_complete }}%</span>
              </div>
            </td>
            <td class="whitespace-nowrap px-4 py-3 text-xs" :class="isOverdue(t) ? 'font-medium text-rose-600 dark:text-rose-400' : 'text-muted'">
              {{ formatDate(t.due_date) }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-end gap-2 text-sm">
      <button
        type="button"
        class="btn-secondary px-3 py-1.5"
        :disabled="page <= 1"
        aria-label="Previous page"
        @click="page--; loadTasks()"
      >
        Previous
      </button>
      <span class="text-muted">Page {{ page }} of {{ totalPages }}</span>
      <button
        type="button"
        class="btn-secondary px-3 py-1.5"
        :disabled="page >= totalPages"
        aria-label="Next page"
        @click="page++; loadTasks()"
      >
        Next
      </button>
    </div>

    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4" @click.self="showCreate = false">
      <div class="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-surface p-6 shadow-xl">
        <h2 class="text-lg font-semibold text-ink">Create task</h2>
        <p class="mt-1 text-sm text-muted">
          New tasks start as drafts. The access policy is established at creation.
        </p>

        <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label class="block sm:col-span-2">
            <span class="text-xs font-medium text-body">Title *</span>
            <input
              v-model="form.title"
              type="text"
              class="input-field mt-1"
              placeholder="What needs to be done?"
            />
          </label>
          <label class="block sm:col-span-2">
            <span class="text-xs font-medium text-body">Description</span>
            <textarea
              v-model="form.description"
              rows="3"
              class="input-field mt-1"
              placeholder="Background, instructions, acceptance expectations"
            />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-body">Priority</span>
            <select v-model="form.priority" class="input-field mt-1">
              <option v-for="p in PRIORITIES" :key="p" :value="p">{{ capitalize(p) }}</option>
            </select>
          </label>
          <label class="block">
            <span class="text-xs font-medium text-body">Accountable PM *</span>
            <select v-model="form.accountable_pm_id" class="input-field mt-1">
              <option value="">Select a person</option>
              <option :value="meId">{{ meName }} (me)</option>
              <option v-for="u in candidatePMs" :key="u.id" :value="u.id">{{ u.full_name }}</option>
            </select>
          </label>
          <label class="block">
            <span class="text-xs font-medium text-body">Start date</span>
            <input v-model="form.start_date" type="date" class="input-field mt-1" />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-body">Due date</span>
            <input v-model="form.due_date" type="date" class="input-field mt-1" />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-body">Visibility</span>
            <select v-model="form.visibility_mode" class="input-field mt-1">
              <option value="participants">Participants (the project team)</option>
              <option value="private">Private (invited people only)</option>
              <option value="department_scoped">Department scoped</option>
              <option value="custom">Custom (explicit grants only)</option>
            </select>
          </label>
          <label v-if="form.visibility_mode === 'department_scoped'" class="block">
            <span class="text-xs font-medium text-body">Department *</span>
            <select v-model="form.department_id" class="input-field mt-1">
              <option value="">Select a department</option>
              <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </label>
        </div>

        <p v-if="createError" role="alert" class="mt-4 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{{ createError }}</p>

        <div class="mt-6 flex justify-end gap-3">
          <button type="button" class="btn-secondary" @click="showCreate = false">
            Cancel
          </button>
          <button type="button" class="btn-primary" :disabled="creating" @click="createTask">
            {{ creating ? 'Creating' : 'Create task' }}
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
const capitalize = (v: string) => v.charAt(0).toUpperCase() + v.slice(1)
const priorityTone = (p: string) =>
  p === 'critical' ? 'rose' : p === 'high' ? 'amber' : p === 'medium' ? 'gray' : 'green'

const hasActiveFilters = computed(() =>
  Boolean(query.value.trim() || statusFilter.value || priorityFilter.value))

function clearFilters() {
  query.value = ''
  statusFilter.value = ''
  priorityFilter.value = ''
  page.value = 1
  loadTasks()
}

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
  try {
    const users = await api.get<{ items: { id: string, full_name: string, account_status: string }[] }>('/api/v1/users?page_size=100')
    candidatePMs.value = users.items
      .filter(u => u.account_status === 'active' && u.id !== meId.value)
      .map(u => ({ id: u.id, full_name: u.full_name }))
  } catch {
    // The directory requires users.manage; hide the options when absent.
  }
  try {
    departments.value = await api.get<Department[]>('/api/v1/departments')
  } catch {
    // Departments require departments.manage; hide the options when absent.
  }
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
