<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <nav class="text-xs text-muted" aria-label="Breadcrumb">Administration / Audit log</nav>
    <div class="mt-1 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="page-title">Audit log</h1>
        <p class="page-subtitle">
          {{ securityOnly ? 'Security events: sign-ins, passwords, two-factor, sessions and access changes.' : 'Every recorded change, newest first. Entries cannot be edited or deleted.' }}
        </p>
      </div>
      <button type="button" class="btn-secondary" :disabled="exporting" @click="exportCsv">
        {{ exporting ? 'Preparing' : 'Export CSV' }}
      </button>
    </div>

    <form class="card mt-5 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5" role="search" @submit.prevent="apply">
      <div class="lg:col-span-2">
        <label for="q" class="block text-xs font-medium text-muted">Search</label>
        <input id="q" v-model="filters.q" type="search" class="input-field mt-1" placeholder="Summary, action or record id">
      </div>
      <div>
        <label for="area" class="block text-xs font-medium text-muted">Area</label>
        <select id="area" v-model="filters.action" class="input-field mt-1">
          <option v-for="o in areaOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div>
        <label for="since" class="block text-xs font-medium text-muted">From</label>
        <input id="since" v-model="filters.since" type="date" class="input-field mt-1">
      </div>
      <div>
        <label for="until" class="block text-xs font-medium text-muted">To</label>
        <input id="until" v-model="filters.until" type="date" class="input-field mt-1">
      </div>
      <div class="flex gap-2 sm:col-span-2 lg:col-span-5">
        <button type="submit" class="btn-primary">Apply filters</button>
        <button v-if="hasFilters" type="button" class="btn-ghost" @click="reset">Clear</button>
        <span class="ml-auto self-center text-sm text-muted" aria-live="polite">{{ total }} event{{ total === 1 ? '' : 's' }}</span>
      </div>
    </form>

    <p v-if="error" role="alert" class="alert-error mt-4">{{ error }}</p>

    <div class="card mt-4 overflow-x-auto">
      <table class="min-w-full divide-y divide-line text-sm">
        <caption class="sr-only">Audit events</caption>
        <thead class="table-head">
          <tr>
            <th scope="col" class="px-4 py-3">When</th>
            <th scope="col" class="px-4 py-3">Who</th>
            <th scope="col" class="px-4 py-3">Action</th>
            <th scope="col" class="px-4 py-3">Details</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-line">
          <tr v-if="loading"><td colspan="4" class="px-4 py-6"><div class="h-8 animate-pulse rounded bg-hover" aria-busy="true" /></td></tr>
          <tr v-else-if="!events.length"><td colspan="4"><div class="empty-state">No events match these filters.</div></td></tr>
          <tr v-for="e in events" :key="e.id" class="align-top">
            <td class="table-cell whitespace-nowrap text-xs text-muted">{{ formatDateTime(e.occurred_at) }}</td>
            <td class="table-cell">
              <p class="text-body">{{ e.actor_name || 'System' }}</p>
              <p v-if="e.actor_email" class="text-xs text-muted">{{ e.actor_email }}</p>
            </td>
            <td class="table-cell"><AppBadge :tone="tone(e.action)">{{ e.action }}</AppBadge></td>
            <td class="table-cell">
              <p class="text-body">{{ describe(e) }}</p>
              <p v-if="e.reason" class="text-xs text-muted">Reason: {{ e.reason }}</p>
              <details v-if="Object.keys(e.metadata).length || e.request_id" class="mt-1 text-xs text-muted">
                <summary class="cursor-pointer select-none hover:text-ink">More</summary>
                <pre class="mt-1 max-w-xl overflow-x-auto whitespace-pre-wrap rounded bg-hover p-2 text-[11px] text-body">{{ JSON.stringify({ resource: `${e.resource_type}:${e.resource_id ?? ''}`, request_id: e.request_id, ...e.metadata }, null, 2) }}</pre>
              </details>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="pages > 1" class="mt-4 flex items-center justify-end gap-2 text-sm">
      <button type="button" class="btn-secondary px-3 py-1.5" :disabled="page <= 1" aria-label="Previous page" @click="go(page - 1)">Previous</button>
      <span class="text-muted">Page {{ page }} of {{ pages }}</span>
      <button type="button" class="btn-secondary px-3 py-1.5" :disabled="page >= pages" aria-label="Next page" @click="go(page + 1)">Next</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ApiError } from '~/composables/useApi'
import type { BadgeTone } from '~/utils/display'

useHead({ title: 'Audit log - DecOps' })

interface AuditEventRow {
  id: string, occurred_at: string, action: string, resource_type: string, resource_id: string | null,
  actor_name: string | null, actor_email: string | null, change_summary: string | null,
  reason: string | null, request_id: string | null, metadata: Record<string, unknown>
}

const api = useApi()
const auth = useAuth()
const securityOnly = computed(() => !auth.hasPermission('audit.read'))

const allAreas = [
  { value: '', label: 'All areas' }, { value: 'auth.', label: 'Sign-in' }, { value: 'password.', label: 'Passwords' },
  { value: 'mfa.', label: 'Two-factor' }, { value: 'session.', label: 'Sessions' }, { value: 'user.', label: 'Users' },
  { value: 'role.', label: 'Roles' }, { value: 'task.', label: 'Tasks' }, { value: 'import.', label: 'Imports' },
  { value: 'settings.', label: 'Settings' },
]
const businessAreas = ['task.', 'import.']
const areaOptions = computed(() => allAreas.filter(a => !securityOnly.value || !businessAreas.includes(a.value)))

const filters = reactive({ q: '', action: '', since: '', until: '' })
const events = ref<AuditEventRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const loading = ref(true)
const exporting = ref(false)
const error = ref('')
const hasFilters = computed(() => !!(filters.q || filters.action || filters.since || filters.until))

function query(extra: Record<string, string> = {}): string {
  const p = new URLSearchParams(extra)
  if (filters.q.trim()) p.set('q', filters.q.trim())
  if (filters.action) p.set('action', filters.action)
  if (filters.since) p.set('since', `${filters.since}T00:00:00`)
  if (filters.until) p.set('until', `${filters.until}T23:59:59`)
  return p.toString()
}

async function load() {
  loading.value = true
  try {
    const r = await api.get<{ items: AuditEventRow[], total: number }>(
      `/api/v1/audit/events?${query({ page: String(page.value), page_size: String(pageSize) })}`)
    events.value = r.items; total.value = r.total; error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the audit log.'
  } finally { loading.value = false }
}
function apply() { page.value = 1; void load() }
function reset() { Object.assign(filters, { q: '', action: '', since: '', until: '' }); apply() }
function go(n: number) { page.value = n; void load() }

async function exportCsv() {
  exporting.value = true
  try {
    const { blob, filename } = await api.downloadGet(`/api/v1/audit/events/export?${query()}`)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Export failed.'
  } finally { exporting.value = false }
}

const LABELS: Record<string, string> = {
  'auth.login': 'Signed in', 'auth.logout': 'Signed out', 'auth.login_failed': 'Failed sign-in attempt',
  'auth.login_rejected': 'Sign-in refused (account locked or inactive)',
  'password.changed': 'Changed their password', 'password.change_failed': 'Wrong current password entered',
  'password.reset_requested': 'Requested a password reset link', 'password.reset_completed': 'Reset their password',
  'mfa.enabled': 'Turned on two-factor sign-in', 'mfa.disabled': 'Turned off two-factor sign-in',
  'mfa.admin_reset': 'Two-factor was reset by an administrator', 'mfa.recovery_code_used': 'Signed in with a recovery code',
  'session.revoked': 'Signed out a device', 'session.revoked_others': 'Signed out all other devices',
  'user.password_change_required': 'Required to choose a new password',
}

function describe(e: AuditEventRow): string {
  return e.change_summary || LABELS[e.action] || `${e.resource_type} ${e.action.split('.').slice(1).join(' ')}`.trim()
}

function tone(action: string): BadgeTone {
  if (/failed|rejected|locked|revoked|deleted|disabled|reset/.test(action)) return 'rose'
  if (action.startsWith('auth.') || action.startsWith('mfa.') || action.startsWith('password.')) return 'blue'
  if (action.startsWith('user.') || action.startsWith('role.')) return 'violet'
  return 'gray'
}

onMounted(load)
</script>
