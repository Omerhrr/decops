<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <!-- Welcome -->
    <section class="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-xl font-semibold text-slate-900">Welcome back, {{ firstName }}</h1>
          <p class="mt-1 text-sm text-slate-500">
            Signed in as {{ auth.user.value?.email }} · {{ auth.user.value?.employee_code }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <AppBadge tone="green">{{ systemHealth }}</AppBadge>
          <NuxtLink
            to="/my-tasks"
            class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700"
          >
            My Tasks →
          </NuxtLink>
        </div>
      </div>
    </section>

    <!-- Loading state -->
    <div v-if="pending" class="mt-6 rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
      Loading your dashboard…
    </div>

    <template v-else-if="summary">
      <!-- Personal stat cards -->
      <section class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="My work overview">
        <StatCard label="Assigned to me" :value="summary.me.assigned_active" icon="📋"
                  note="Active accountable + supporting assignments" />
        <StatCard label="Accountable for" :value="summary.me.accountable_active" icon="🎯"
                  note="Tasks where you are the accountable PM" />
        <StatCard label="Overdue" :value="summary.me.overdue" icon="⏰"
                  :note="summary.me.overdue ? 'Action needed - past due date' : 'Nothing past due'" />
        <StatCard label="Blocked" :value="summary.me.blocked" icon="⛔"
                  :note="`${summary.me.due_soon} due within 7 days`" />
      </section>

      <!-- Management overview (dashboards.view holders only) -->
      <section
        v-if="summary.management_overview"
        class="mt-6 rounded-2xl border border-brand-200 bg-brand-50/40 p-6"
        aria-label="Management overview"
      >
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold text-slate-900">Management overview</h2>
            <p class="mt-1 text-sm text-slate-500">
              Aggregated over the {{ summary.visible_total }} task(s) you are authorized to view.
            </p>
          </div>
          <NuxtLink to="/reports" class="text-sm font-medium text-brand-700 hover:underline">
            Open reports →
          </NuxtLink>
        </div>
        <div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div class="rounded-xl bg-white p-4">
            <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Visible tasks</p>
            <p class="mt-1 text-2xl font-semibold text-slate-900">{{ summary.management_overview.total_visible }}</p>
          </div>
          <div class="rounded-xl bg-white p-4">
            <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Active</p>
            <p class="mt-1 text-2xl font-semibold text-slate-900">{{ summary.management_overview.active }}</p>
          </div>
          <div class="rounded-xl bg-white p-4">
            <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Overdue</p>
            <p class="mt-1 text-2xl font-semibold" :class="summary.management_overview.overdue ? 'text-rose-600' : 'text-slate-900'">
              {{ summary.management_overview.overdue }}
            </p>
          </div>
          <div class="rounded-xl bg-white p-4">
            <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Completion rate</p>
            <p class="mt-1 text-2xl font-semibold text-slate-900">{{ summary.management_overview.completion_rate }}%</p>
          </div>
          <div class="rounded-xl bg-white p-4">
            <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Completed · 7 days</p>
            <p class="mt-1 text-2xl font-semibold text-slate-900">{{ summary.management_overview.completed_this_week }}</p>
          </div>
        </div>
      </section>

      <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Upcoming deadlines -->
        <section class="rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-2" aria-label="Upcoming deadlines">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold text-slate-900">Upcoming deadlines</h2>
            <AppBadge tone="gray">{{ summary.upcoming_deadlines.length }} scheduled</AppBadge>
          </div>
          <p class="mt-1 text-sm text-slate-500">Active work due in the next 30 days, soonest first.</p>
          <ul class="mt-4 divide-y divide-slate-100">
            <li v-if="!summary.upcoming_deadlines.length" class="py-6 text-sm text-slate-400">
              No upcoming deadlines in your authorized tasks.
            </li>
            <li v-for="row in summary.upcoming_deadlines" :key="row.task_id" class="flex items-center justify-between gap-4 py-3">
              <div class="min-w-0">
                <NuxtLink :to="`/tasks/${row.task_id}`" class="truncate text-sm font-medium text-slate-800 hover:text-brand-700">
                  {{ row.title }}
                </NuxtLink>
                <p class="mt-0.5 text-xs text-slate-400">
                  {{ row.task_number }} · {{ row.accountable_pm?.full_name ?? 'Unassigned' }}
                </p>
              </div>
              <div class="shrink-0 text-right">
                <AppBadge :tone="deadlineTone(row.days_left)">{{ dueLabel(row.days_left) }}</AppBadge>
                <p class="mt-1 text-xs text-slate-400">{{ formatDate(row.due_date) }}</p>
              </div>
            </li>
          </ul>
        </section>

        <!-- Blocked work -->
        <section class="rounded-2xl border border-slate-200 bg-white p-6" aria-label="Blocked work">
          <h2 class="text-base font-semibold text-slate-900">Blocked work</h2>
          <p class="mt-1 text-sm text-slate-500">Tasks currently waiting on a blocker.</p>
          <ul class="mt-4 space-y-3">
            <li v-if="!summary.blocked_tasks.length" class="py-4 text-sm text-slate-400">
              Nothing blocked right now.
            </li>
            <li v-for="row in summary.blocked_tasks" :key="row.task_id"
                class="rounded-xl border border-rose-100 bg-rose-50/60 p-3">
              <NuxtLink :to="`/tasks/${row.task_id}`" class="text-sm font-medium text-slate-800 hover:text-brand-700">
                {{ row.title }}
              </NuxtLink>
              <p class="mt-0.5 text-xs text-slate-500">{{ row.task_number }}</p>
            </li>
          </ul>
        </section>
      </div>

      <!-- Recent authorized activity -->
      <section class="mt-6 rounded-2xl border border-slate-200 bg-white p-6" aria-label="Recent activity">
        <h2 class="text-base font-semibold text-slate-900">Recent authorized activity</h2>
        <p class="mt-1 text-sm text-slate-500">
          Latest events across tasks you can view - restricted tasks never appear here.
        </p>
        <ul class="mt-4 space-y-3">
          <li v-if="!summary.recent_activity.length" class="py-4 text-sm text-slate-400">
            No activity yet.
          </li>
          <li v-for="(event, i) in summary.recent_activity" :key="i" class="flex items-start gap-3 rounded-xl bg-slate-50 p-3">
            <div class="min-w-0 flex-1">
              <p class="text-sm text-slate-700">
                <span class="font-medium">{{ event.actor?.full_name ?? 'System' }}</span>
 - {{ event.summary }}
              </p>
              <p class="mt-0.5 text-xs text-slate-400">
                <NuxtLink :to="`/tasks/${event.task_id}`" class="hover:text-brand-700">
                  {{ event.task_number }} · {{ event.task_title }}
                </NuxtLink>
                · {{ formatDateTime(event.created_at) }}
              </p>
            </div>
            <AppBadge tone="gray">{{ event.activity_type }}</AppBadge>
          </li>
        </ul>
      </section>
    </template>

    <!-- Administration quick links (permission-gated) -->
    <section
      v-if="auth.hasPermission('users.manage', 'departments.manage')"
      class="mt-6 rounded-2xl border border-slate-200 bg-white p-6"
      aria-label="Administration"
    >
      <h2 class="text-base font-semibold text-slate-900">Administration</h2>
      <p class="mt-1 text-sm text-slate-500">
        Identity administration is permission-gated - these areas are audited.
      </p>
      <div class="mt-4 flex flex-wrap gap-3">
        <NuxtLink
          v-if="auth.hasPermission('users.manage')"
          to="/admin/users"
          class="rounded-xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition-colors hover:border-brand-300 hover:bg-brand-50"
        >
          👥 User administration →
        </NuxtLink>
        <NuxtLink
          v-if="auth.hasPermission('departments.manage', 'users.manage')"
          to="/admin/departments"
          class="rounded-xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition-colors hover:border-brand-300 hover:bg-brand-50"
        >
          🏢 Department management →
        </NuxtLink>
      </div>
    </section>

    <!-- Roadmap -->
    <section class="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
      <h2 class="text-base font-semibold text-slate-900">Implementation roadmap</h2>
      <p class="mt-1 text-sm text-slate-500">
        Shipped so far: authentication, identity & authorization, task management,
        workflow engine, collaboration, and dashboards & reporting.
      </p>
      <ol class="mt-5 space-y-3">
        <li
          v-for="item in roadmap"
          :key="item.phase"
          class="flex items-start gap-3 rounded-xl border border-slate-100 p-3"
          :class="item.done ? 'bg-brand-50/50' : 'bg-white'"
        >
          <span
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
            :class="item.done ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500'"
          >
            {{ item.phase }}
          </span>
          <div>
            <p class="text-sm font-medium text-slate-800">
              {{ item.name }}
              <AppBadge v-if="item.done" tone="green" class="ml-2">Shipped</AppBadge>
              <AppBadge v-else tone="gray" class="ml-2">Planned</AppBadge>
            </p>
            <p class="mt-0.5 text-xs text-slate-500">{{ item.detail }}</p>
          </div>
        </li>
      </ol>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { DashboardSummary } from '~/types/api'

const auth = useAuth()
const api = useApi()
const firstName = computed(() => auth.displayName.value.split(' ')[0] || 'there')

const { data: health } = await useFetch('/api/v1/health', { lazy: true })
const systemHealth = computed(() =>
  health.value ? `System: ${health.value.status} (${health.value.environment})` : 'System status unknown',
)

// Dashboard aggregates are computed server-side from the actor's authorized
// task set (same engine as the register), so totals reconcile by construction.
const { data: summary, pending } = await useFetch<DashboardSummary>('/api/v1/dashboard/summary')

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
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const roadmap = [
  { phase: 2, name: 'Application Foundation', detail: 'Auth, users/sessions, RBAC seeds, migrations, audit log, tests', done: true },
  { phase: 3, name: 'Identity & Authorization', detail: 'User/department administration, task access policies, isolation tests', done: true },
  { phase: 4, name: 'Task Management', detail: 'Task register, detail pages, assignments, lifecycle transitions', done: true },
  { phase: 5, name: 'Workflow Engine', detail: 'Stages, milestones, subtasks, dependencies, progress calculation', done: true },
  { phase: 6, name: 'Collaboration & Notifications', detail: 'Comments, attachments, notification center, outbox worker', done: true },
  { phase: 7, name: 'Dashboards & Reporting', detail: 'Personal/management dashboards, department workspace, reports, authorized CSV exports', done: true },
  { phase: 8, name: 'CSV Migration', detail: 'Import center: mapping, preview, validation, reconciliation', done: false },
]

useHead({ title: 'Dashboard - DecOps' })
</script>
