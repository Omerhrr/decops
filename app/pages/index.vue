<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-xs font-medium uppercase tracking-wider text-slate-400">{{ todayLabel }}</p>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
          Welcome back, {{ firstName }}
        </h1>
        <div class="mt-2 flex flex-wrap items-center gap-1.5">
          <AppBadge v-for="role in auth.roleNames.value" :key="role" tone="blue">{{ role }}</AppBadge>
          <AppBadge v-if="!auth.roleNames.value.length" tone="gray">No roles assigned</AppBadge>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <span class="inline-flex items-center gap-2 text-sm text-slate-500">
          <span class="relative flex h-2.5 w-2.5">
            <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-60" />
            <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-500" />
          </span>
          All systems operational
        </span>
        <NuxtLink to="/my-tasks" class="btn-primary">
          My Tasks
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
          </svg>
        </NuxtLink>
      </div>
    </section>

    <div v-if="pending" class="mt-8 space-y-6" aria-busy="true" aria-label="Loading dashboard">
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div v-for="i in 4" :key="i" class="card p-6">
          <div class="h-3 w-24 animate-pulse rounded bg-slate-200" />
          <div class="mt-3 h-8 w-16 animate-pulse rounded bg-slate-200" />
          <div class="mt-4 h-2.5 w-32 animate-pulse rounded bg-slate-100" />
        </div>
      </div>
      <div class="card p-6">
        <div class="h-3 w-40 animate-pulse rounded bg-slate-200" />
        <div class="mt-4 space-y-3">
          <div v-for="i in 3" :key="i" class="h-12 animate-pulse rounded-lg bg-slate-100" />
        </div>
      </div>
    </div>

    <template v-else-if="summary">
      <section class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="My work overview">
        <StatCard label="Assigned to me" :value="summary.me.assigned_active"
                  note="Active accountable and supporting assignments" />
        <StatCard label="Accountable for" :value="summary.me.accountable_active"
                  note="Tasks where you are the accountable PM" tone="positive" />
        <StatCard label="Overdue" :value="summary.me.overdue" :tone="summary.me.overdue ? 'danger' : 'neutral'"
                  :note="summary.me.overdue ? 'Action needed: past due date' : 'Nothing past due'" />
        <StatCard label="Blocked" :value="summary.me.blocked" :tone="summary.me.blocked ? 'warning' : 'neutral'"
                  :note="`${summary.me.due_soon} due within 7 days`" />
      </section>

      <section
        v-if="summary.management_overview"
        class="card mt-6 p-5 sm:p-6"
        aria-label="Management overview"
      >
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="text-base font-semibold text-slate-900">Management overview</h2>
            <p class="page-subtitle">
              Aggregated over the {{ summary.visible_total }} task(s) you are authorized to view.
            </p>
          </div>
          <NuxtLink to="/reports" class="text-sm font-medium text-brand-700 hover:underline">
            Open reports
          </NuxtLink>
        </div>
        <div class="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-slate-200 sm:grid-cols-3 lg:grid-cols-5">
          <div v-for="cell in managementCells" :key="cell.label" class="bg-white p-4">
            <p class="text-xs font-medium uppercase tracking-wide text-slate-400">{{ cell.label }}</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight" :class="cell.danger ? 'text-rose-600' : 'text-slate-900'">
              {{ cell.value }}
            </p>
          </div>
        </div>
      </section>

      <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section class="card p-5 sm:p-6 lg:col-span-2" aria-label="Upcoming deadlines">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold text-slate-900">Upcoming deadlines</h2>
            <AppBadge tone="gray">{{ summary.upcoming_deadlines.length }} scheduled</AppBadge>
          </div>
          <p class="page-subtitle">Active work due in the next 30 days, soonest first.</p>
          <ul class="mt-4 divide-y divide-slate-100">
            <li v-if="!summary.upcoming_deadlines.length" class="empty-state">
              <svg class="mx-auto h-8 w-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
              </svg>
              <p class="mt-2">No upcoming deadlines in your authorized tasks.</p>
            </li>
            <li v-for="row in summary.upcoming_deadlines" :key="row.task_id"
                class="flex items-center justify-between gap-4 py-3">
              <div class="min-w-0">
                <NuxtLink :to="`/tasks/${row.task_id}`"
                          class="truncate text-sm font-medium text-slate-800 hover:text-brand-700">
                  {{ row.title }}
                </NuxtLink>
                <p class="mt-0.5 text-xs text-slate-500">
                  {{ row.task_number }} · {{ row.accountable_pm?.full_name ?? 'Unassigned' }}
                </p>
              </div>
              <div class="shrink-0 text-right">
                <AppBadge :tone="deadlineTone(row.days_left)">{{ dueLabel(row.days_left) }}</AppBadge>
                <p class="mt-1 text-xs text-slate-500">{{ formatDate(row.due_date) }}</p>
              </div>
            </li>
          </ul>
        </section>

        <section class="card p-5 sm:p-6" aria-label="Blocked work">
          <h2 class="text-base font-semibold text-slate-900">Blocked work</h2>
          <p class="page-subtitle">Tasks currently waiting on a blocker.</p>
          <ul class="mt-4 space-y-3">
            <li v-if="!summary.blocked_tasks.length" class="empty-state">
              <svg class="mx-auto h-8 w-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9.143 17.082a24.248 24.248 0 003.844.148m-3.844-.148a23.856 23.856 0 01-5.455-1.31 8.964 8.964 0 002.3-6.022l-.112-.07a2.25 2.25 0 01.85-4.066A48.513 48.513 0 0012 5.25c1.268 0 2.52.05 3.75.15a2.25 2.25 0 01.85 4.066l-.111.07a8.964 8.964 0 002.301 6.022 23.856 23.856 0 01-5.455 1.31m-3.843-.148a24.31 24.31 0 013.843.148m0 0v3.75a2.25 2.25 0 01-4.5 0v-3.75" />
              </svg>
              <p class="mt-2">Nothing blocked right now.</p>
            </li>
            <li v-for="row in summary.blocked_tasks" :key="row.task_id"
                class="rounded-xl border border-rose-100 bg-rose-50/60 p-3">
              <NuxtLink :to="`/tasks/${row.task_id}`"
                        class="text-sm font-medium text-slate-800 hover:text-brand-700">
                {{ row.title }}
              </NuxtLink>
              <p class="mt-0.5 text-xs text-slate-500">{{ row.task_number }}</p>
            </li>
          </ul>
        </section>
      </div>

      <section class="card mt-6 p-5 sm:p-6" aria-label="Recent activity">
        <h2 class="text-base font-semibold text-slate-900">Recent activity</h2>
        <p class="page-subtitle">
          Latest events across tasks you can view; restricted tasks never appear here.
        </p>
        <ul class="mt-4 space-y-2">
          <li v-if="!summary.recent_activity.length" class="empty-state">
            <p>No activity yet.</p>
          </li>
          <li v-for="(event, i) in summary.recent_activity" :key="i"
              class="flex items-start gap-3 rounded-xl border border-slate-100 p-3 transition-colors hover:bg-slate-50">
            <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="activityDot(event.activity_type)" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <p class="text-sm text-slate-700">
                <span class="font-medium text-slate-900">{{ event.actor?.full_name ?? 'System' }}</span>
                {{ event.summary }}
              </p>
              <p class="mt-0.5 text-xs text-slate-500">
                <NuxtLink :to="`/tasks/${event.task_id}`" class="hover:text-brand-700">
                  {{ event.task_number }} · {{ event.task_title }}
                </NuxtLink>
                · {{ formatRelative(event.created_at) }}
              </p>
            </div>
            <AppBadge tone="gray">{{ activityLabel(event.activity_type) }}</AppBadge>
          </li>
        </ul>
      </section>
    </template>

    <section
      v-if="auth.hasPermission('users.manage', 'departments.manage')"
      class="card mt-6 p-5 sm:p-6"
      aria-label="Administration"
    >
      <h2 class="text-base font-semibold text-slate-900">Administration</h2>
      <p class="page-subtitle">Identity administration is permission-gated; these areas are audited.</p>
      <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <NuxtLink
          v-if="auth.hasPermission('users.manage')"
          to="/admin/users"
          class="group flex items-center gap-4 rounded-xl border border-slate-200 p-4 transition-colors hover:border-brand-300 hover:bg-brand-50/50"
        >
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
          </span>
          <span>
            <span class="block text-sm font-medium text-slate-900">User administration</span>
            <span class="block text-xs text-slate-500">Accounts, roles and access</span>
          </span>
        </NuxtLink>
        <NuxtLink
          v-if="auth.hasPermission('departments.manage', 'users.manage')"
          to="/admin/departments"
          class="group flex items-center gap-4 rounded-xl border border-slate-200 p-4 transition-colors hover:border-brand-300 hover:bg-brand-50/50"
        >
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21" />
            </svg>
          </span>
          <span>
            <span class="block text-sm font-medium text-slate-900">Department management</span>
            <span class="block text-xs text-slate-500">Structure and memberships</span>
          </span>
        </NuxtLink>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { DashboardSummary } from '~/types/api'

const auth = useAuth()
const firstName = computed(() => auth.displayName.value.split(' ')[0] || 'there')

const todayLabel = new Date().toLocaleDateString(undefined, {
  weekday: 'long', month: 'long', day: 'numeric',
})

// Dashboard aggregates are computed server-side from the actor's authorized
// task set (same engine as the register), so totals reconcile by construction.
const { data: summary, pending } = await useFetch<DashboardSummary>('/api/v1/dashboard/summary')

const managementCells = computed(() => {
  const o = summary.value?.management_overview
  if (!o) return []
  return [
    { label: 'Visible tasks', value: o.total_visible, danger: false },
    { label: 'Active', value: o.active, danger: false },
    { label: 'Overdue', value: o.overdue, danger: o.overdue > 0 },
    { label: 'Completion rate', value: `${o.completion_rate}%`, danger: false },
    { label: 'Completed · 7 days', value: o.completed_this_week, danger: false },
  ]
})

function deadlineTone(daysLeft: number): 'green' | 'amber' | 'rose' {
  if (daysLeft < 0) return 'rose'
  if (daysLeft <= 7) return 'amber'
  return 'green'
}

function dueLabel(daysLeft: number): string {
  if (daysLeft < 0) return `${Math.abs(daysLeft)}d overdue`
  if (daysLeft === 0) return 'Due today'
  return `in ${daysLeft}d`
}

function formatDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

function formatRelative(value: string): string {
  const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const ACTIVITY_LABELS: Record<string, string> = {
  'task.created': 'Created',
  'task.updated': 'Updated',
  'task.assigned': 'Assigned',
  'task.status_changed': 'Status',
  'task.commented': 'Comment',
  'task.attachment_added': 'Attachment',
  'task.access_granted': 'Access',
  'task.imported': 'Imported',
}

function activityLabel(type: string): string {
  return ACTIVITY_LABELS[type] ?? type.replaceAll('_', ' ')
}

function activityDot(type: string): string {
  if (type === 'task.status_changed' || type === 'task.created') return 'bg-brand-500'
  if (type === 'task.access_granted') return 'bg-sky-500'
  return 'bg-slate-300'
}

useHead({ title: 'Dashboard - DecOps' })
</script>
