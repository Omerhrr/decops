<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <div v-if="pending" class="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
      Loading workspace…
    </div>
    <div v-else-if="error" class="rounded-2xl border border-slate-200 bg-white p-10 text-center">
      <p class="text-sm font-medium text-slate-700">Workspace unavailable</p>
      <p class="mt-1 text-sm text-slate-400">This department may not exist or you lack reporting access.</p>
    </div>

    <template v-else-if="workspace">
      <section class="card p-5 sm:p-6">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <NuxtLink to="/departments" class="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-3.5 w-3.5" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
              All departments
            </NuxtLink>
            <h1 class="mt-1 text-xl font-semibold text-slate-900">{{ workspace.department.name }}</h1>
            <p class="mt-1 text-sm text-slate-500">
              Lead: {{ workspace.department.lead ?? '-' }} · {{ workspace.department.member_count }} member(s)
            </p>
          </div>
          <AppBadge tone="gray">{{ workspace.active_total }} active task(s) visible to you</AppBadge>
        </div>
      </section>

      <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section class="rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-2" aria-label="Department tasks">
          <h2 class="text-base font-semibold text-slate-900">Departmental tasks</h2>
          <p class="mt-1 text-sm text-slate-500">Authorized tasks associated with this department.</p>
          <ul class="mt-4 divide-y divide-slate-100">
            <li v-if="!workspace.tasks.length" class="py-6 text-sm text-slate-400">No tasks associated with this department.</li>
            <li v-for="task in workspace.tasks" :key="task.id" class="flex items-center justify-between gap-4 py-3">
              <div class="min-w-0">
                <NuxtLink :to="`/tasks/${task.id}`" class="truncate text-sm font-medium text-slate-800 hover:text-brand-700">
                  {{ task.title }}
                </NuxtLink>
                <p class="mt-0.5 text-xs text-slate-400">
                  {{ task.task_number }} · {{ task.accountable_pm ?? 'Unassigned' }}
                </p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <AppBadge :tone="statusTone(task.status)">{{ prettyStatus(task.status) }}</AppBadge>
                <AppBadge :tone="priorityTone(task.priority)">{{ task.priority }}</AppBadge>
              </div>
            </li>
          </ul>
        </section>

        <div class="space-y-6">
          <section class="rounded-2xl border border-slate-200 bg-white p-6" aria-label="Upcoming deadlines">
            <h2 class="text-base font-semibold text-slate-900">Upcoming deadlines</h2>
            <ul class="mt-3 space-y-2">
              <li v-if="!workspace.upcoming.length" class="text-sm text-slate-400">Nothing scheduled.</li>
              <li v-for="row in workspace.upcoming" :key="row.id" class="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                <NuxtLink :to="`/tasks/${row.id}`" class="truncate text-sm text-slate-700 hover:text-brand-700">
                  {{ row.task_number }} · {{ row.title }}
                </NuxtLink>
                <span class="shrink-0 text-xs text-slate-400">{{ formatDate(row.due_date) }}</span>
              </li>
            </ul>
          </section>

          <section class="rounded-2xl border border-slate-200 bg-white p-6" aria-label="Blocked and overdue">
            <h2 class="text-base font-semibold text-slate-900">Needs attention</h2>
            <h3 class="mt-3 text-xs font-semibold uppercase tracking-wide text-rose-500">Blocked ({{ workspace.blocked.length }})</h3>
            <ul class="mt-2 space-y-2">
              <li v-if="!workspace.blocked.length" class="text-sm text-slate-400">Nothing blocked.</li>
              <li v-for="row in workspace.blocked" :key="row.id" class="rounded-lg border border-rose-100 bg-rose-50/60 px-3 py-2">
                <NuxtLink :to="`/tasks/${row.id}`" class="text-sm text-slate-700 hover:text-brand-700">
                  {{ row.task_number }} · {{ row.title }}
                </NuxtLink>
              </li>
            </ul>
            <h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-rose-500">Overdue ({{ workspace.overdue.length }})</h3>
            <ul class="mt-2 space-y-2">
              <li v-if="!workspace.overdue.length" class="text-sm text-slate-400">Nothing overdue.</li>
              <li v-for="row in workspace.overdue" :key="row.id" class="rounded-lg border border-rose-100 bg-rose-50/60 px-3 py-2">
                <NuxtLink :to="`/tasks/${row.id}`" class="text-sm text-slate-700 hover:text-brand-700">
                  {{ row.task_number }} · {{ row.title }}
                </NuxtLink>
                <span class="ml-2 text-xs text-rose-500">due {{ formatDate(row.due_date) }}</span>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <section class="mt-6 rounded-2xl border border-slate-200 bg-white p-6" aria-label="Team assignments">
        <h2 class="text-base font-semibold text-slate-900">Team assignments</h2>
        <p class="mt-1 text-sm text-slate-500">
          Open assignments across the authorized tasks of this department.
        </p>
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr class="text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                <th class="px-4 py-3">Member</th>
                <th class="px-4 py-3">Role</th>
                <th class="px-4 py-3">Open assignments</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-if="!workspace.team.length">
                <td colspan="3" class="px-4 py-8 text-center text-slate-400">No members in this department.</td>
              </tr>
              <tr v-for="entry in workspace.team" :key="entry.user.id">
                <td class="px-4 py-3">
                  <p class="font-medium text-slate-800">{{ entry.user.full_name }}</p>
                  <p class="text-xs text-slate-400">{{ entry.user.email }} · {{ entry.user.employee_code }}</p>
                </td>
                <td class="px-4 py-3"><AppBadge :tone="entry.membership_role === 'lead' ? 'green' : 'gray'">{{ entry.membership_role }}</AppBadge></td>
                <td class="px-4 py-3 text-slate-700">{{ entry.open_assignments }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { DepartmentWorkspace } from '~/types/api'

const route = useRoute()

const { data: workspace, pending, error } = await useFetch<DepartmentWorkspace>(
  () => `/api/v1/reports/departments/${route.params.id}/workspace`,
)

function statusTone(status: string): 'green' | 'amber' | 'gray' | 'rose' {
  if (status === 'completed') return 'green'
  if (status === 'blocked') return 'rose'
  if (status === 'in_progress' || status === 'under_review') return 'amber'
  return 'gray'
}

function priorityTone(priority: string): 'green' | 'amber' | 'gray' | 'rose' {
  if (priority === 'critical') return 'rose'
  if (priority === 'high') return 'amber'
  if (priority === 'low') return 'gray'
  return 'green'
}

function prettyStatus(status: string): string {
  return status.replace(/_/g, ' ')
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

useHead({ title: 'Department Workspace - DecOps' })
</script>
