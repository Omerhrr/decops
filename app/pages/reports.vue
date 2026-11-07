<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="rounded-2xl border border-line bg-surface p-6 sm:p-8">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-xl font-semibold text-ink">Reports</h1>
          <p class="mt-1 text-sm text-muted">
            Authorized reporting only - every figure is computed from the tasks your access
            policy allows, and exports are audited.
          </p>
        </div>
        <div v-if="auth.hasPermission('exports.approved')" class="flex flex-wrap gap-2">
          <span
            v-for="option in exportOptions"
            :key="option.type"
            class="inline-flex overflow-hidden rounded-lg border border-brand-200 dark:border-brand-500/40"
          >
            <button
              type="button"
              class="bg-brand-50 px-3 py-2 text-sm font-medium text-brand-700 transition-colors hover:bg-brand-100 disabled:opacity-50 dark:bg-brand-500/10 dark:text-brand-300 dark:hover:bg-brand-500/15"
              :disabled="exporting === `${option.type}:csv`"
              @click="runExport(option.type, 'csv')"
            >
              {{ exporting === `${option.type}:csv` ? 'Preparing…' : option.label }}
            </button>
            <button
              type="button"
              class="border-l border-brand-200 bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-700 transition-colors hover:bg-brand-100 disabled:opacity-50 dark:border-brand-500/40 dark:bg-brand-500/10 dark:text-brand-300 dark:hover:bg-brand-500/15"
              :aria-label="`${option.label} as PDF`"
              :disabled="exporting === `${option.type}:pdf`"
              @click="runExport(option.type, 'pdf')"
            >
              {{ exporting === `${option.type}:pdf` ? '…' : 'PDF' }}
            </button>
          </span>
        </div>
      </div>
      <p v-if="exportError" role="alert" class="alert-error mt-4">{{ exportError }}</p>
    </section>

    <!-- Not authorized -->
    <section v-if="!canSeeCompletion && !canSeeWorkload" class="mt-6 rounded-2xl border border-line bg-surface p-10 text-center">
      <p class="text-sm font-medium text-body">No reporting access</p>
      <p class="mt-1 text-sm text-faint">
        Reporting is available to roles with reporting access.
        {{ auth.hasPermission('exports.approved') ? 'You can still use the export buttons above.' : 'Ask an administrator if you need it.' }}
      </p>
    </section>

    <div class="mt-6 grid grid-cols-1 gap-6">
      <!-- Completion trend -->
      <section v-if="canSeeCompletion" class="rounded-2xl border border-line bg-surface p-6" aria-label="Task completion report">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="text-base font-semibold text-ink">Task completion trend</h2>
            <p class="mt-1 text-sm text-muted">
              Created vs completed per week over the last {{ completion?.weeks }} weeks.
            </p>
          </div>
          <div v-if="completion" class="flex flex-wrap gap-4 text-xs text-muted">
            <span>Avg cycle: <strong>{{ completion.avg_days_to_complete ?? '-' }}d</strong></span>
          </div>
        </div>

        <div v-if="completion" class="mt-6">
          <ChartTrend :data="completion.series" label="Weekly tasks created versus completed" />

          <div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div class="rounded-xl bg-elevated p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-faint">Completed in window</p>
              <p class="mt-1 text-xl font-semibold text-ink">{{ completion.totals.completed_in_window }}</p>
            </div>
            <div class="rounded-xl bg-elevated p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-faint">Active now</p>
              <p class="mt-1 text-xl font-semibold text-ink">{{ completion.totals.active }}</p>
            </div>
            <div class="rounded-xl bg-elevated p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-faint">Overdue</p>
              <p class="mt-1 text-xl font-semibold" :class="completion.totals.overdue ? 'text-rose-600 dark:text-rose-400' : 'text-ink'">
                {{ completion.totals.overdue }}
              </p>
            </div>
            <div class="rounded-xl bg-elevated p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-faint">Milestones done</p>
              <p class="mt-1 text-xl font-semibold text-ink">
                {{ completion.milestone_progress.completed }}/{{ completion.milestone_progress.total }}
              </p>
            </div>
          </div>

          <!-- Blocker analysis -->
          <div class="mt-6 rounded-xl border border-line p-4">
            <h3 class="text-sm font-semibold text-ink">Blocker analysis</h3>
            <p class="mt-1 text-xs text-muted">
              {{ completion.blocker_analysis.blocked_total }} blocked task(s),
              {{ completion.blocker_analysis.overdue_blocked }} of them past due.
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <AppBadge v-for="(count, priority) in completion.blocker_analysis.by_priority" :key="priority" tone="rose">
                {{ priority }}: {{ count }}
              </AppBadge>
              <AppBadge v-for="(count, dept) in completion.blocker_analysis.by_department" :key="dept" tone="amber">
                {{ dept }}: {{ count }}
              </AppBadge>
              <span v-if="!completion.blocker_analysis.blocked_total" class="text-xs text-faint">Nothing blocked.</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Department workload -->
      <section v-if="canSeeWorkload" class="rounded-2xl border border-line bg-surface p-6" aria-label="Department workload report">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold text-ink">Department workload</h2>
            <p class="mt-1 text-sm text-muted">
              {{ workload?.scope === 'all' ? 'All departments (management scope).' : 'Departments you lead or belong to.' }}
            </p>
          </div>
          <NuxtLink to="/departments" class="inline-flex items-center gap-1 text-sm font-medium text-brand-700 dark:text-brand-300 hover:underline">
            Open workspaces
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          </NuxtLink>
        </div>

        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-line text-sm">
            <thead>
              <tr class="text-left text-xs font-semibold uppercase tracking-wide text-faint">
                <th class="px-4 py-3">Department</th>
                <th class="px-4 py-3">Lead</th>
                <th class="px-4 py-3">Members</th>
                <th class="px-4 py-3">Active</th>
                <th class="px-4 py-3">Overdue</th>
                <th class="px-4 py-3">Blocked</th>
                <th class="px-4 py-3">Completed</th>
                <th class="px-4 py-3">Assignments</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-if="!workload?.departments.length">
                <td colspan="8" class="px-4 py-8 text-center text-faint">No departments in your reporting scope.</td>
              </tr>
              <tr v-for="row in workload?.departments" :key="row.department_id" class="transition-colors hover:bg-hover">
                <td class="px-4 py-3">
                  <NuxtLink :to="`/departments/${row.department_id}`" class="font-medium text-ink hover:text-brand-700 dark:hover:text-brand-300">
                    {{ row.department_name }}
                  </NuxtLink>
                </td>
                <td class="px-4 py-3 text-body">{{ row.lead ?? '-' }}</td>
                <td class="px-4 py-3 text-body">{{ row.member_count }}</td>
                <td class="px-4 py-3 text-ink">{{ row.active_tasks }}</td>
                <td class="px-4 py-3">
                  <span :class="row.overdue_tasks ? 'font-semibold text-rose-600 dark:text-rose-400' : 'text-body'">{{ row.overdue_tasks }}</span>
                </td>
                <td class="px-4 py-3">
                  <span :class="row.blocked_tasks ? 'font-semibold text-amber-600 dark:text-amber-400' : 'text-body'">{{ row.blocked_tasks }}</span>
                </td>
                <td class="px-4 py-3 text-body">{{ row.completed_tasks }}</td>
                <td class="px-4 py-3 text-body">{{ row.open_assignments }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TaskCompletionReport, DepartmentWorkloadReport } from '~/types/api'

const auth = useAuth()
const api = useApi()

const canSeeCompletion = computed(() => auth.hasPermission('reports.view'))
const canSeeWorkload = computed(() => auth.hasPermission('reports.view', 'reports.department.view'))

const { data: completion } = await useFetch<TaskCompletionReport>('/api/v1/reports/task-completion', {
  query: { weeks: 12 },
  // 404 for users without reports.view - swallow into null instead of surfacing an error.
  server: false,
})
const { data: workload } = await useFetch<DepartmentWorkloadReport>('/api/v1/reports/department-workload', {
  server: false,
})

// CSV and PDF exports (exports.approved; audited server-side). PDFs use the
// organization's saved document design from Settings.
const exportOptions = [
  { type: 'task_register', label: 'Task register' },
  { type: 'department_workload', label: 'Department workload' },
  { type: 'task_completion', label: 'Completion trend' },
] as const
const exporting = ref<string | null>(null)
const exportError = ref('')

async function runExport(type: string, format: 'csv' | 'pdf') {
  exporting.value = `${type}:${format}`
  exportError.value = ''
  try {
    const { blob, filename } = await api.download('/api/v1/reports/exports', {
      export_type: type,
      format,
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    exportError.value = err instanceof Error ? err.message : 'Export failed.'
  } finally {
    exporting.value = null
  }
}

useHead({ title: 'Reports - DecOps' })
</script>
