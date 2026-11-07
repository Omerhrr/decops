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
          Every task your role and assignments give you access to, checked per task.
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
        <option v-for="s in STATUSES" :key="s" :value="s">{{ capitalize(statusLabel(s)) }}</option>
      </select>
      <select v-model="priorityFilter" class="select-field" aria-label="Filter by priority" @change="loadTasks">
        <option value="">All priorities</option>
        <option v-for="p in PRIORITIES" :key="p" :value="p">{{ capitalize(p) }}</option>
      </select>
      <span class="text-sm text-muted sm:ml-auto">{{ total }} task{{ total === 1 ? '' : 's' }}</span>
    </section>

    <div class="mt-3 inline-flex rounded-xl border border-line bg-surface p-0.5 text-sm" role="group" aria-label="Task view">
      <button v-for="v in VIEWS" :key="v.key" type="button" class="rounded-lg px-3 py-1.5" :class="view === v.key ? 'bg-brand-500 text-white' : 'text-muted hover:text-ink'" :aria-pressed="view === v.key" :data-test="`view-${v.key}`" @click="setView(v.key)">{{ v.label }}</button>
    </div>
    <p v-if="boardMessage" class="mt-2 text-sm text-rose-600 dark:text-rose-400" role="alert">{{ boardMessage }}</p>

    <section class="mt-3 flex flex-wrap items-center gap-2 text-sm" aria-label="Saved filters and export">
      <select v-if="savedFilters.length" class="select-field !w-auto" aria-label="Apply a saved filter" v-model="selectedSaved" @change="applySaved">
        <option value="">Saved filters…</option>
        <option v-for="f in savedFilters" :key="f.id" :value="f.id">{{ f.name }}</option>
      </select>
      <button v-if="selectedSaved" type="button" class="btn-secondary px-3 py-1.5" @click="deleteSaved">Delete saved filter</button>
      <template v-if="hasActiveFilters">
        <input v-if="savingFilter" v-model="newFilterName" type="text" maxlength="80" class="input-field !w-48" placeholder="Filter name" aria-label="Saved filter name" @keydown.enter.prevent="saveFilter" />
        <button type="button" class="btn-secondary px-3 py-1.5" @click="savingFilter ? saveFilter() : (savingFilter = true)">
          {{ savingFilter ? 'Save' : 'Save this filter' }}
        </button>
      </template>
      <button v-if="canExport" type="button" class="btn-secondary ml-auto px-3 py-1.5" :disabled="exporting" @click="exportCsv">
        {{ exporting ? 'Exporting…' : 'Export CSV' }}
      </button>
    </section>

    <section v-if="selected.size" class="mt-3 flex flex-wrap items-center gap-2 rounded-2xl border border-brand-500/40 bg-surface p-3 text-sm" aria-live="polite" data-test="bulk-bar">
      <span class="font-medium text-ink">{{ selected.size }} selected</span>
      <select v-model="bulkStatus" class="select-field !w-auto" aria-label="Move selected tasks to status">
        <option value="">Change status…</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ capitalize(statusLabel(s)) }}</option>
      </select>
      <button type="button" class="btn-secondary px-3 py-1.5" :disabled="!bulkStatus || bulking" @click="runBulk('transition')">Apply status</button>
      <select v-model="bulkPriority" class="select-field !w-auto" aria-label="Set priority of selected tasks">
        <option value="">Set priority…</option>
        <option v-for="p in PRIORITIES" :key="p" :value="p">{{ capitalize(p) }}</option>
      </select>
      <button type="button" class="btn-secondary px-3 py-1.5" :disabled="!bulkPriority || bulking" @click="runBulk('set_priority')">Apply priority</button>
      <button type="button" class="ml-auto text-xs text-muted hover:text-body" @click="selected.clear()">Clear selection</button>
    </section>
    <p v-if="bulkMessage" class="mt-2 text-sm text-muted" role="status">{{ bulkMessage }}</p>

    <TaskBoard v-if="view === 'board'" :tasks="tasks" @move="moveTask" />
    <TaskCalendar v-else-if="view === 'calendar'" :tasks="tasks" />

    <!-- Phone layout: one card per task (the 8-column table is unreadable at 390px) -->
    <ul v-show="view === 'list'" class="mt-4 space-y-3 sm:hidden" aria-label="Tasks">
      <li v-if="loading" class="h-24 animate-pulse rounded-2xl bg-hover" aria-busy="true" />
      <li v-else-if="!tasks.length" class="card empty-state">
        <p>No authorized tasks match the filters.</p>
        <button v-if="hasActiveFilters" type="button" class="btn-secondary mt-3" @click="clearFilters">Clear filters</button>
      </li>
      <li v-for="t in tasks" :key="t.id" class="card p-4">
        <div class="flex items-start justify-between gap-3">
          <input type="checkbox" class="mt-1 h-4 w-4" :checked="selected.has(t.id)" :aria-label="`Select ${t.task_number}`" @change="toggle(t.id)" />
          <NuxtLink :to="`/tasks/${t.id}`" class="min-w-0 flex-1 font-medium text-ink">{{ t.title }}</NuxtLink>
          <span class="shrink-0 font-mono text-xs text-muted">{{ t.task_number }}</span>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-1.5">
          <AppBadge :tone="statusTone(t.status)">{{ statusLabel(t.status) }}</AppBadge>
          <AppBadge :tone="priorityTone(t.priority)">{{ capitalize(t.priority) }}</AppBadge>
          <AppBadge v-for="name in t.department_names" :key="name" tone="gray">{{ name }}</AppBadge>
        </div>
        <div class="mt-3 flex items-center justify-between gap-3 text-xs text-muted">
          <span>{{ t.accountable_pm?.full_name ?? 'Unassigned' }}</span>
          <span :class="isOverdue(t.due_date, t.status) ? 'font-medium text-rose-600 dark:text-rose-400' : ''">Due {{ formatDate(t.due_date) }}</span>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-hover" role="progressbar" :aria-valuenow="t.percent_complete" aria-valuemin="0" aria-valuemax="100">
            <div class="h-full rounded-full bg-brand-500" :style="{ width: `${t.percent_complete}%` }" />
          </div>
          <span class="text-xs text-muted">{{ t.percent_complete }}%</span>
        </div>
      </li>
    </ul>

    <section v-show="view === 'list'" class="mt-4 hidden overflow-x-auto rounded-2xl border border-line bg-surface sm:block">
      <table class="min-w-full divide-y divide-line text-sm">
        <thead class="bg-elevated text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th class="w-10 px-4 py-3"><input type="checkbox" class="h-4 w-4" :checked="allSelected" aria-label="Select all tasks on this page" @change="toggleAll" /></th>
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
            <td colspan="9" class="px-4 py-2">
              <div class="space-y-2 py-2" aria-busy="true" aria-label="Loading tasks">
                <div v-for="i in 5" :key="i" class="h-10 animate-pulse rounded-lg bg-hover" />
              </div>
            </td>
          </tr>
          <tr v-else-if="!tasks.length">
            <td colspan="9">
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
            <td class="px-4 py-3" @click.stop><input type="checkbox" class="h-4 w-4" :checked="selected.has(t.id)" :aria-label="`Select ${t.task_number}`" @change="toggle(t.id)" /></td>
            <td class="table-cell whitespace-nowrap font-mono text-xs text-body">{{ t.task_number }}</td>
            <td class="table-cell">
              <NuxtLink :to="`/tasks/${t.id}`" class="font-medium text-ink hover:text-brand-700 dark:hover:text-brand-300" @click.stop>
                {{ t.title }}
              </NuxtLink>
              <p class="text-xs text-muted">{{ visibilityLabel(t.visibility_mode) }}</p>
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
            <td class="whitespace-nowrap px-4 py-3 text-xs" :class="isOverdue(t.due_date, t.status) ? 'font-medium text-rose-600 dark:text-rose-400' : 'text-muted'">
              {{ formatDate(t.due_date) }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="view === 'list' && totalPages > 1" class="mt-4 flex items-center justify-end gap-2 text-sm">
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

    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4" role="dialog" aria-modal="true" aria-label="Create task" v-dialog="{ close: () => showCreate = false }" @click.self="showCreate = false">
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
              <option value="department_scoped">Departments (members of assigned departments)</option>
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

interface SavedFilter { id: string, name: string, params: Record<string, string> }
interface BulkResponse { succeeded: number, failed: number, results: { task_id: string, ok: boolean, error?: string }[] }

const api = useApi()
const auth = useAuth()

const STATUSES: TaskStatus[] = ['draft', 'open', 'in_progress', 'blocked', 'under_review', 'completed', 'cancelled', 'archived']
const PRIORITIES: TaskPriority[] = ['low', 'medium', 'high', 'critical']

const tasks = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const VIEWS = [{ key: 'list', label: 'List' }, { key: 'board', label: 'Board' }, { key: 'calendar', label: 'Calendar' }] as const
const view = ref<'list' | 'board' | 'calendar'>('list')
const boardMessage = ref('')
const pageSize = computed(() => (view.value === 'list' ? 25 : 100))
const loading = ref(true)
const query = ref('')
const statusFilter = ref('')
const priorityFilter = ref('')

const canCreate = computed(() => auth.hasPermission('tasks.create'))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

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

const hasActiveFilters = computed(() =>
  Boolean(query.value.trim() || statusFilter.value || priorityFilter.value))

function clearFilters() {
  query.value = ''
  statusFilter.value = ''
  priorityFilter.value = ''
  page.value = 1
  loadTasks()
}

function openTask(id: string) {
  navigateTo(`/tasks/${id}`)
}

async function loadTasks() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))
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

// ---- saved filters ----
const savedFilters = ref<SavedFilter[]>([])
const selectedSaved = ref('')
const savingFilter = ref(false)
const newFilterName = ref('')

async function loadSaved() {
  try { savedFilters.value = await api.get<SavedFilter[]>('/api/v1/saved-filters') } catch { savedFilters.value = [] }
}
async function saveFilter() {
  const name = newFilterName.value.trim()
  if (!name) return
  const params: Record<string, string> = {}
  if (query.value.trim()) params.q = query.value.trim()
  if (statusFilter.value) params.status = statusFilter.value
  if (priorityFilter.value) params.priority = priorityFilter.value
  try {
    await api.post('/api/v1/saved-filters', { name, params })
    newFilterName.value = ''
    savingFilter.value = false
    await loadSaved()
  } catch { /* leave the form open so the user can retry */ }
}
function applySaved() {
  const f = savedFilters.value.find(x => x.id === selectedSaved.value)
  if (!f) return
  query.value = f.params.q ?? ''
  statusFilter.value = f.params.status ?? ''
  priorityFilter.value = f.params.priority ?? ''
  page.value = 1
  loadTasks()
}
async function deleteSaved() {
  if (!selectedSaved.value) return
  try { await api.delete(`/api/v1/saved-filters/${selectedSaved.value}`) } catch { /* ignore */ }
  selectedSaved.value = ''
  await loadSaved()
}

// ---- export ----
const canExport = computed(() => auth.hasPermission('exports.approved'))
const exporting = ref(false)
async function exportCsv() {
  exporting.value = true
  try {
    const { blob, filename } = await api.download('/api/v1/reports/exports', {
      export_type: 'task_register', format: 'csv',
      q: query.value.trim() || null, status: statusFilter.value || null, priority: priorityFilter.value || null,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch { /* the register stays usable; export needs exports.approved */ } finally {
    exporting.value = false
  }
}

// ---- bulk actions ----
const selected = reactive(new Set<string>())
const bulkStatus = ref('')
const bulkPriority = ref('')
const bulking = ref(false)
const bulkMessage = ref('')
const allSelected = computed(() => tasks.value.length > 0 && tasks.value.every(t => selected.has(t.id)))
function toggle(id: string) { if (selected.has(id)) selected.delete(id); else selected.add(id) }
function toggleAll() {
  if (allSelected.value) tasks.value.forEach(t => selected.delete(t.id))
  else tasks.value.forEach(t => selected.add(t.id))
}
async function runBulk(action: 'transition' | 'set_priority') {
  bulking.value = true
  bulkMessage.value = ''
  try {
    const res = await api.post<BulkResponse>('/api/v1/tasks/bulk', {
      task_ids: [...selected], action,
      to_status: action === 'transition' ? bulkStatus.value : undefined,
      priority: action === 'set_priority' ? bulkPriority.value : undefined,
    })
    const firstError = res.results.find(r => !r.ok)?.error
    bulkMessage.value = `${res.succeeded} updated${res.failed ? `, ${res.failed} skipped${firstError ? ` (${firstError})` : ''}` : ''}.`
    selected.clear()
    bulkStatus.value = ''
    bulkPriority.value = ''
    await loadTasks()
  } catch (err) {
    bulkMessage.value = err instanceof Error ? err.message : 'Bulk update failed.'
  } finally {
    bulking.value = false
  }
}

function setView(v: 'list' | 'board' | 'calendar') {
  view.value = v
  boardMessage.value = ''
  page.value = 1
  try { localStorage.setItem('decops.tasks.view', v) } catch { /* optional */ }
  loadTasks()
}
async function moveTask(id: string, status: string) {
  boardMessage.value = ''
  try {
    await api.post(`/api/v1/tasks/${id}/transition`, { to_status: status })
  } catch (err) {
    boardMessage.value = err instanceof Error ? err.message : 'That move is not allowed.'
  }
  await loadTasks()
}

onMounted(() => {
  try {
    const saved = localStorage.getItem('decops.tasks.view')
    if (saved === 'board' || saved === 'calendar') view.value = saved
  } catch { /* optional */ }
  loadTasks()
  loadSaved()
})
useHead({ title: 'Task register - DecOps' })
</script>
